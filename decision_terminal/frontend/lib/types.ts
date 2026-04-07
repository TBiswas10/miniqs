type RiskCheck = {
  key: string;
  label: string;
  passed: boolean;
  reason: string;
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

export type DecisionPayload = {
  decision: {
    signal: {
      side: "BUY" | "SELL" | "HOLD";
      confidence: number;
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
      risk: {
        confidence_threshold: number;
        max_position_size: number;
        max_daily_loss: number;
      };
    };
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
  strategy_intelligence: Array<{
    strategy: string;
    trades: number;
    win_rate: number;
    total_pnl: number;
    confidence_avg: number;
    trend: Array<{ ts: string; pnl: number; confidence: number }>;
  }>;
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
