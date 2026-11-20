from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.config import load_strategy, resolve_settings
from app.database import (PositionAudit, PositionQualityReview, StrategyScan,
                          NewsArticle, get_database)
from app.market import MarketDataProvider
from app.paper_store import PaperStore
from app.trading import Order, OrderAction, PaperPortfolio
from app.ai import PositionQualityReview as PositionQualityReviewSchema
from app.ai_coordinator import (AIInferenceCoordinator, AIInferenceBudgetExceeded,
                                AIInferenceUnavailable)
from app.ai import PromptManager


class ActivePositionScan:
    def __init__(self, paper: PaperPortfolio | None = None):
        env, app, _ = resolve_settings()
        self.env = env
        self.app = app
        self.paper = paper or PaperStore().load(PaperPortfolio(
            env.paper_initial_capital,
            env.paper_slippage_bps,
            env.paper_commission_per_order,
        ))
        self.store = PaperStore()
        self.market = MarketDataProvider(env.quote_max_age_seconds if hasattr(env, "quote_max_age_seconds") else 300)

    def _quality_review(self, coordinator: AIInferenceCoordinator, symbol: str,
                        position: dict, quote: dict, stop: dict | None,
                        strategy) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=strategy.catalyst_freshness_hours)
        _, session_factory = get_database()
        with session_factory() as session:
            articles = session.query(NewsArticle).filter(
                NewsArticle.symbol == symbol,
                NewsArticle.retrieved_at >= cutoff,
            ).order_by(NewsArticle.retrieved_at.desc()).limit(5).all()
        if not articles:
            return {
                "symbol": symbol,
                "catalyst_identifiable": "false",
                "catalyst_fresh": "false",
                "catalyst_priced_in": "unknown",
                "reward_risk_ratio": None,
                "decision": "HOLD",
                "evidence": {"reason": "No fresh structured catalyst evidence"},
                "ai_output": None,
            }

        stop_price = stop["stop_price"] if stop else (
            position["average_cost"] * (1 - strategy.stop_loss_percent / 100)
        )
        downside = max(float(quote["price"]) - float(stop_price), 0)
        upside = max(float(quote["price"]) * 0.05, 0)
        reward_risk = round(upside / downside, 4) if downside > 0 else 0
        references = [article.url for article in articles if article.url]
        evidence = {
            "symbol": symbol,
            "current_price": quote["price"],
            "stop_price": stop_price,
            "upside_estimate": upside,
            "downside_estimate": downside,
            "reward_risk_ratio": reward_risk,
            "fresh_article_count": len(articles),
            "source_references": references,
        }

        prompt = PromptManager().render("analysis/position_quality.md", {
            "symbol": symbol,
            "structured_evidence": evidence,
        })
        try:
            review = asyncio.run(coordinator.analyze(
                prompt,
                PositionQualityReviewSchema,
                lightweight=True,
            ))
        except (AIInferenceUnavailable, AIInferenceBudgetExceeded) as exc:
            # Ollama cannot authorize entries or AI-driven closes. Protective
            # stop exits are handled before this review and remain available.
            return {
                "symbol": symbol,
                "catalyst_identifiable": "true",
                "catalyst_fresh": "true",
                "catalyst_priced_in": "unknown",
                "reward_risk_ratio": reward_risk,
                "decision": "HOLD",
                "evidence": evidence,
                "ai_output": {"status": "unavailable", "error": exc.__class__.__name__},
            }

        catalyst_ok = (review.catalyst_identifiable
                       and review.catalyst_fresh
                       and review.catalyst_priced_in is not True)
        reward_ok = review.reward_risk_ratio >= strategy.minimum_reward_risk_ratio
        decision = "CLOSE" if (
            review.decision == "CLOSE"
            and catalyst_ok
            and reward_ok
        ) else "HOLD"
        return {
            "symbol": symbol,
            "catalyst_identifiable": str(review.catalyst_identifiable).lower(),
            "catalyst_fresh": str(review.catalyst_fresh).lower(),
            "catalyst_priced_in": (
                str(review.catalyst_priced_in).lower()
                if review.catalyst_priced_in is not None else "unknown"
            ),
            "reward_risk_ratio": review.reward_risk_ratio,
            "decision": decision,
            "evidence": evidence,
            "ai_output": review.model_dump(),
        }

    def run(self, scan_name: str) -> dict:
        strategy = load_strategy()
        coordinator = AIInferenceCoordinator(self.env)
        coordinator.reset_scan()
        if not self.app.paper_trading:
            raise RuntimeError("Active intraday live execution is not implemented")
        _, session_factory = get_database()
        with session_factory() as session:
            scan = StrategyScan(scan_name=scan_name, status="running", payload={})
            session.add(scan)
            session.commit()
            scan_id = scan.id

        audits = []
        exits = []
        reviews = []

        # Account reconciliation and the stop audit are deliberately first.
        for symbol, position in list(self.paper.positions.items())[:strategy.max_positions_reviewed_per_scan]:
            existing = self.paper.stop_orders.get(symbol)
            if existing is None:
                stop_price = position["average_cost"] * (1 - strategy.stop_loss_percent / 100)
                placed = self.paper.place_stop(symbol, stop_price)
                audits.append({
                    "symbol": symbol,
                    "stop_status": "placed",
                    "stop_order_id": f"paper-{symbol}",
                    "action": "protect",
                    "reason": placed,
                })
            else:
                if existing["quantity"] != position["quantity"]:
                    stop_price = position["average_cost"] * (1 - strategy.stop_loss_percent / 100)
                    placed = self.paper.place_stop(symbol, stop_price)
                    audits.append({
                        "symbol": symbol,
                        "stop_status": "replaced",
                        "stop_order_id": f"paper-{symbol}",
                        "action": "protect",
                        "reason": placed,
                    })
                else:
                    audits.append({
                        "symbol": symbol,
                        "stop_status": "confirmed",
                        "stop_order_id": f"paper-{symbol}",
                        "action": "hold",
                        "reason": "Paper stop matches position",
                    })

        self.store.save(self.paper)

        for symbol, position in list(self.paper.positions.items())[:strategy.max_positions_reviewed_per_scan]:
            quote = self.market.quote(symbol)
            if not quote or not self.market.quote_is_fresh(quote):
                audits.append({
                    "symbol": symbol,
                    "stop_status": "unverified",
                    "stop_order_id": f"paper-{symbol}",
                    "action": "hold",
                    "reason": "Stale or unavailable quote; no entry or close action",
                })
                continue

            stop = self.paper.stop_orders.get(symbol)
            if stop and quote["price"] <= stop["stop_price"]:
                if len(exits) >= strategy.max_exits_per_scan:
                    continue
                order = Order(
                    symbol=symbol,
                    side=OrderAction.SELL,
                    quantity=position["quantity"],
                    quote_price=quote["price"],
                    idempotency_key=f"paper-stop:{symbol}:{position['quantity']}:{stop['stop_price']}",
                    is_exit=True,
                )
                result = self.paper.submit(order)
                if result["status"] == "filled":
                    self.store.record_order(
                        symbol,
                        "SELL",
                        position["quantity"],
                        result,
                        order.idempotency_key,
                    )
                    del self.paper.stop_orders[symbol]
                    exits.append({"symbol": symbol, "reason": "stop_triggered", "result": result})
                    continue

            review = self._quality_review(
                coordinator,
                symbol,
                position,
                quote,
                stop,
                strategy,
            )
            reviews.append(review)

            if (review["decision"] == "CLOSE"
                    and len(exits) < strategy.max_exits_per_scan):
                order = Order(
                    symbol=symbol,
                    side=OrderAction.SELL,
                    quantity=position["quantity"],
                    quote_price=quote["price"],
                    idempotency_key=f"quality-close:{symbol}:{position['quantity']}",
                    is_exit=True,
                )
                result = self.paper.submit(order)
                if result["status"] == "filled":
                    self.store.record_order(
                        symbol,
                        "SELL",
                        position["quantity"],
                        result,
                        order.idempotency_key,
                    )
                    del self.paper.stop_orders[symbol]
                    exits.append({"symbol": symbol, "reason": "quality_close", "result": result})

        self.store.save(self.paper)

        with session_factory() as session:
            for audit in audits:
                session.add(PositionAudit(
                    scan_id=scan_id,
                    symbol=audit["symbol"],
                    stop_status=audit["stop_status"],
                    stop_order_id=audit.get("stop_order_id"),
                    action=audit["action"],
                    reason=str(audit["reason"]),
                ))
            for review in reviews:
                session.add(PositionQualityReview(
                    scan_id=scan_id,
                    symbol=review["symbol"],
                    catalyst_identifiable=review["catalyst_identifiable"],
                    catalyst_fresh=review["catalyst_fresh"],
                    catalyst_priced_in=review["catalyst_priced_in"],
                    reward_risk_ratio=review["reward_risk_ratio"],
                    decision=review["decision"],
                    evidence=review["evidence"],
                    ai_output=review["ai_output"],
                ))
            scan = session.query(StrategyScan).filter_by(id=scan_id).first()
            scan.finished_at = datetime.now(timezone.utc)
            scan.status = "completed"
            scan.payload = {
                "audits": audits,
                "exits": exits,
                "reviews": reviews,
                "paper_trading": self.app.paper_trading,
            }
            session.commit()

        return {
            "scan_name": scan_name,
            "status": "completed",
            "audits": audits,
            "exits": exits,
            "reviews": reviews,
        }
