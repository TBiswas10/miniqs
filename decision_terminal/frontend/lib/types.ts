type RiskCheck = {
  key: string;
  label: string;
  passed: boolean;
  reason: string;
};

type ConfidenceBreakdown = {
  signal_strength: number;
  agreement: number;
  regime_fit: number;
  historical_edge: number;
  final: number;
};

type HistoryRow = {
  ts: string;
  symbol: string;
  signal: string;
  action: string;
  strategy: string;
  confidence: number;
  pnl: number;
  price: number;
  reason: string;
  risk_checks: RiskCheck[];
  raw: Record<string, unknown>;
};

export type RiskControls = {
  confidence_threshold: number;
  max_position_size: number;
  max_daily_loss: number;
  risk_per_trade?: number;
  daily_loss_limit?: number;
  max_exposure?: number;
  max_concurrent_positions?: number;
  cooldown_seconds?: number;
  max_loss_per_session?: number;
  portfolio_drawdown_limit?: number;
  per_strategy_drawdown_limit?: number;
  extreme_loss_kill_switch?: number;
  strategy_kill_loss?: number;
  vol_target?: number;
  vol_floor?: number;
  vol_ceiling?: number;
  low_vol_multiplier?: number;
  high_vol_multiplier?: number;
  min_trade_size?: number;
  max_trade_size?: number;
  [key: string]: number | undefined;
};

export type DecisionPayload = {
  decision: {
    signal: {
      side: "BUY" | "SELL" | "HOLD";
      confidence: ConfidenceBreakdown;
      strategy: string;
      reason: string;
      timestamp: string;
      trend: Array<{ idx: number; signal: string; confidence: number }>;
    };
    checks: RiskCheck[];
    decision: {
      action: "EXECUTE" | "BLOCKED" | "HOLD";
      stage: string;
      reason: string;
      pipeline: Record<string, "done" | "blocked" | "idle">;
    };
    position: {
      symbol: string;
      size: number;
      price: number;
    };
    account: {
      equity: number;
      pnl: number;
      executed_trades: number;
      cash: number;
      open_orders: Array<{
        id: string;
        status: string;
        symbol: string;
        price: number;
      }>;
      pnl_spark: Array<{ idx: number; pnl: number }>;
    };
  };
  meta: {
    connected: boolean;
    connection_event: string;
    reconnects: number;
    last_tick_age_sec: number | null;
    controls: {
      trading_enabled: boolean;
      kill_switch: boolean;
      strategies: Record<string, boolean>;
      risk: RiskControls;
    };
    app_contract?: {
      strategy_registry: string[];
      risk_parameters: string[];
      missing_strategy_controls: string[];
    };
  };
  risk_state: {
    halted: boolean;
    kill_switch: boolean;
    trading_enabled: boolean;
    confidence_threshold: number;
    max_position_size: number;
    daily_loss_limit: number;
    risk_per_trade: number;
    max_exposure: number;
    cooldown_seconds: number;
    portfolio_drawdown_limit: number;
    latest_risk_type: string;
    latest_risk_reason: string;
    latest_risk_severity: string;
  };
  thought_stream: Array<{
    ts: string;
    level: "info" | "warn" | "error";
    stage: string;
    message: string;
    symbol?: string;
  }>;
  history: HistoryRow[];
  why_not_trade: Array<{
    ts: string;
    action: string;
    checks: RiskCheck[];
    reason: string;
  }>;
  hold_reasons: Array<{
    reason: string;
    impact: number;
  }>;
  strategy_intelligence: Array<{
    strategy: string;
    trades: number;
    win_rate: number;
    total_pnl: number;
    confidence_avg: number;
    trend: Array<{ ts: string; pnl: number; confidence: number }>;
  }>;
  strategy_health: Record<string, {
    participation_rate: number;
    avg_confidence: number;
    recent_hit_rate: number;
    contribution_score: number;
    health_score: number;
    status: "healthy" | "degrading" | "inactive";
  }>;
  risk_debug: {
    confidence_gate: { value: number; threshold: number; passed: boolean; delta: number };
    position_limit: { current: number; max: number; passed: boolean; delta: number };
    drawdown_guard: { current_dd: number; max_dd: number; passed: boolean; delta: number };
  };
  decision_inspector: {
    full_object: Record<string, unknown>;
    features: Record<string, unknown>;
    risk_checks: RiskCheck[];
    reasoning: string;
  };
  counterfactuals: Array<{
    ts: string;
    strategy: string;
    side: string;
    entry_price: number;
    simulated_exit_price: number;
    simulated_pnl: number;
    reason_blocked: string;
  }>;
  counterfactual_result: {
    changed_actions: number;
    pnl_original: number;
    pnl_counterfactual: number;
    delta: number;
  };
  performance: {
    win_rate: number;
    avg_profit: number;
    max_drawdown: number;
    sharpe_approx: number;
    equity_curve: Array<{ idx: number; equity: number }>;
  };
  replay: {
    cursor: number;
    length: number;
    timeline: HistoryRow[];
  };
  alerts: Array<{ level: "info" | "warn" | "error"; message: string }>;
};
