from __future__ import annotations

from app.database import (Execution, PaperAccount, PaperPosition, PaperStopOrder,
                          SimulatedOrder, get_database)
from app.trading import PaperPortfolio


class PaperStore:
    def __init__(self, account_name: str = "default"):
        self.account_name = account_name

    def load(self, portfolio: PaperPortfolio) -> PaperPortfolio:
        _, session_factory = get_database()
        with session_factory() as session:
            account = session.query(PaperAccount).filter_by(name=self.account_name).first()
            if account is None:
                self.save(portfolio)
                return portfolio
            positions = {
                row.symbol: {"quantity": row.quantity, "average_cost": row.average_cost}
                for row in session.query(PaperPosition).filter_by(account_name=self.account_name).all()
            }
            portfolio.initial_cash = account.initial_cash
            portfolio.cash = account.cash
            portfolio.realized_pnl = account.realized_pnl
            portfolio.positions = positions
            portfolio.seen_keys = set(account.seen_keys or [])
            portfolio.stop_orders = {
                row.symbol: {
                    "symbol": row.symbol,
                    "quantity": row.quantity,
                    "stop_price": row.stop_price,
                    "status": row.status,
                }
                for row in session.query(PaperStopOrder).filter_by(
                    account_name=self.account_name,
                    status="open",
                ).all()
            }
        return portfolio

    def save(self, portfolio: PaperPortfolio) -> None:
        _, session_factory = get_database()
        with session_factory() as session:
            account = session.query(PaperAccount).filter_by(name=self.account_name).first()
            if account is None:
                account = PaperAccount(
                    name=self.account_name,
                    initial_cash=portfolio.initial_cash,
                    cash=portfolio.cash,
                    realized_pnl=portfolio.realized_pnl,
                    seen_keys=sorted(portfolio.seen_keys),
                )
                session.add(account)
            else:
                account.initial_cash = portfolio.initial_cash
                account.cash = portfolio.cash
                account.realized_pnl = portfolio.realized_pnl
                account.seen_keys = sorted(portfolio.seen_keys)

            session.query(PaperPosition).filter_by(account_name=self.account_name).delete()
            for symbol, position in portfolio.positions.items():
                session.add(PaperPosition(
                    account_name=self.account_name,
                    symbol=symbol,
                    quantity=position["quantity"],
                    average_cost=position["average_cost"],
                ))
            session.query(PaperStopOrder).filter_by(account_name=self.account_name).delete()
            for symbol, stop in portfolio.stop_orders.items():
                session.add(PaperStopOrder(
                    account_name=self.account_name,
                    symbol=symbol,
                    quantity=stop["quantity"],
                    stop_price=stop["stop_price"],
                    status=stop["status"],
                ))
            session.commit()

    def reset(self, initial_cash: float) -> PaperPortfolio:
        _, session_factory = get_database()
        with session_factory() as session:
            session.query(PaperPosition).filter_by(account_name=self.account_name).delete()
            session.query(PaperStopOrder).filter_by(account_name=self.account_name).delete()
            account = session.query(PaperAccount).filter_by(name=self.account_name).first()
            if account is None:
                session.add(PaperAccount(
                    name=self.account_name,
                    initial_cash=initial_cash,
                    cash=initial_cash,
                    realized_pnl=0,
                ))
            else:
                account.initial_cash = initial_cash
                account.cash = initial_cash
                account.realized_pnl = 0
                account.seen_keys = []
            session.commit()
        return PaperPortfolio(initial_cash)

    def record_order(self, symbol: str, side: str, quantity: float,
                     fill: dict, idempotency_key: str) -> None:
        _, session_factory = get_database()
        with session_factory() as session:
            status = fill.get("status", "unknown")
            average_fill = fill.get("average_fill")
            order = session.query(SimulatedOrder).filter_by(
                idempotency_key=idempotency_key
            ).first()
            if order is None:
                order = SimulatedOrder(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    status=status,
                    filled_quantity=quantity if status == "filled" else 0,
                    average_fill=average_fill,
                    idempotency_key=idempotency_key,
                )
                session.add(order)
                session.flush()
            if status == "filled":
                session.add(Execution(
                    order_id=order.id,
                    account_type="paper",
                    symbol=symbol,
                    quantity=quantity,
                    price=average_fill,
                    fee=0,
                ))
            session.commit()
