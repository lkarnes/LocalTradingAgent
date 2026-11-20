from __future__ import annotations

from pathlib import Path

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.sql import func

from app.config import resolve_settings


class Base(DeclarativeBase):
    pass


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())
    account_type = Column(String, nullable=False)
    cash = Column(Float, nullable=False)
    market_value = Column(Float, nullable=False)
    total_value = Column(Float, nullable=False)


class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True)
    account_type = Column(String, nullable=False)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    average_cost = Column(Float, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PaperAccount(Base):
    __tablename__ = "paper_accounts"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, default="default")
    initial_cash = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    realized_pnl = Column(Float, nullable=False, default=0)
    seen_keys = Column(JSON, nullable=False, default=list)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    id = Column(Integer, primary_key=True)
    account_name = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    average_cost = Column(Float, nullable=False)


class MarketData(Base):
    __tablename__ = "market_data"
    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    data_type = Column(String, nullable=False)
    source = Column(String, nullable=False)
    source_timestamp = Column(DateTime)
    retrieved_at = Column(DateTime, server_default=func.now())
    payload = Column(JSON)


class NewsArticle(Base):
    __tablename__ = "news_articles"
    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True)
    source = Column(String, nullable=False)
    url = Column(Text)
    headline = Column(Text)
    published_at = Column(DateTime)
    retrieved_at = Column(DateTime, server_default=func.now())
    content_hash = Column(String, unique=True)


class TradeDecision(Base):
    __tablename__ = "trade_decisions"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())
    symbol = Column(String, nullable=False)
    action = Column(String, nullable=False)
    confidence = Column(Float)
    reasoning = Column(Text)
    model_name = Column(String)
    prompt_versions = Column(JSON)
    config_hash = Column(String)
    risk_result = Column(JSON)
    approval_status = Column(String)


class SimulatedOrder(Base):
    __tablename__ = "simulated_orders"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    limit_price = Column(Float)
    status = Column(String, nullable=False)
    filled_quantity = Column(Float, default=0)
    average_fill = Column(Float)
    idempotency_key = Column(String, unique=True)


class ActualOrder(Base):
    __tablename__ = "actual_orders"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())
    broker = Column(String)
    broker_order_id = Column(String)
    payload = Column(JSON)
    status = Column(String)


class RiskEvent(Base):
    __tablename__ = "risk_events"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())
    event_type = Column(String, nullable=False)
    symbol = Column(String)
    details = Column(JSON)


class AgentHealth(Base):
    __tablename__ = "agent_health"
    id = Column(Integer, primary_key=True)
    checked_at = Column(DateTime, server_default=func.now())
    component = Column(String, nullable=False)
    status = Column(String, nullable=False)
    detail = Column(Text)


class DailyReport(Base):
    __tablename__ = "daily_reports"
    id = Column(Integer, primary_key=True)
    report_date = Column(String, unique=True)
    payload = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class NewsAnalysis(Base):
    __tablename__ = "news_analysis"
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    sentiment = Column(String)
    catalyst = Column(String)
    confidence = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


class Execution(Base):
    __tablename__ = "executions"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, index=True)
    account_type = Column(String)
    symbol = Column(String, index=True)
    quantity = Column(Float)
    price = Column(Float)
    fee = Column(Float, default=0)
    timestamp = Column(DateTime, server_default=func.now())


class DailyPerformance(Base):
    __tablename__ = "daily_performance"
    id = Column(Integer, primary_key=True)
    report_date = Column(String, unique=True)
    starting_value = Column(Float)
    ending_value = Column(Float)
    daily_return = Column(Float)
    realized_pnl = Column(Float)
    unrealized_pnl = Column(Float)


class PerformanceMetrics(Base):
    __tablename__ = "performance_metrics"
    id = Column(Integer, primary_key=True)
    period = Column(String)
    total_return = Column(Float)
    sharpe_ratio = Column(Float)
    volatility = Column(Float)
    max_drawdown = Column(Float)
    win_rate = Column(Float)
    profit_factor = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


class BenchmarkSnapshot(Base):
    __tablename__ = "benchmark_snapshots"
    id = Column(Integer, primary_key=True)
    snapshot_date = Column(String)
    benchmark = Column(String)
    value = Column(Float)
    source = Column(String)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)
    cycle = Column(String)
    status = Column(String)


class AIRun(Base):
    __tablename__ = "ai_runs"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())
    model_name = Column(String)
    prompt_versions = Column(JSON)
    status = Column(String)
    input_hash = Column(String)


class AIReviewCache(Base):
    __tablename__ = "ai_review_cache"
    id = Column(Integer, primary_key=True)
    input_hash = Column(String, unique=True, nullable=False, index=True)
    model_name = Column(String, nullable=False)
    response = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
    version_hash = Column(String)
    content = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class ConfigurationVersion(Base):
    __tablename__ = "configuration_versions"
    id = Column(Integer, primary_key=True)
    config_hash = Column(String, unique=True)
    effective_config = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class PaperEvaluation(Base):
    __tablename__ = "paper_evaluations"
    id = Column(Integer, primary_key=True)
    evaluation_key = Column(String, unique=True, nullable=False)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)
    status = Column(String, nullable=False)
    starting_value = Column(Float)
    ending_value = Column(Float)
    payload = Column(JSON)


class PaperStopOrder(Base):
    __tablename__ = "paper_stop_orders"
    id = Column(Integer, primary_key=True)
    account_name = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    stop_price = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="open")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class StrategyScan(Base):
    __tablename__ = "strategy_scans"
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)
    scan_name = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)
    payload = Column(JSON)


class PositionAudit(Base):
    __tablename__ = "position_audits"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, index=True)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float)
    cost_basis = Column(Float)
    stop_status = Column(String, nullable=False)
    stop_order_id = Column(String)
    action = Column(String)
    reason = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class PositionQualityReview(Base):
    __tablename__ = "position_quality_reviews"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, index=True)
    symbol = Column(String, nullable=False, index=True)
    catalyst_identifiable = Column(String)
    catalyst_fresh = Column(String)
    catalyst_priced_in = Column(String)
    reward_risk_ratio = Column(Float)
    decision = Column(String)
    evidence = Column(JSON)
    ai_output = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


def get_database():
    env, _, _ = resolve_settings()
    url = env.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite:///./"):
        Path("data").mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
