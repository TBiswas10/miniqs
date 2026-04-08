"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { DecisionPayload, RiskControls } from "@/lib/types";
import { API_BASE, WS_BASE } from "@/lib/config";

const fallback: DecisionPayload = {
  decision: {
    signal: { side: "HOLD", confidence: 0, strategy: "pending", reason: "Waiting for stream", timestamp: "--", trend: [] },
    checks: [],
    decision: { action: "HOLD", stage: "idle", reason: "Waiting for stream", pipeline: { signal: "idle", decision: "idle", sent: "idle", filled: "idle" } },
    position: { symbol: "BTC/USD", size: 0, price: 0 },
    account: { equity: 0, pnl: 0, executed_trades: 0, cash: 0, open_orders: [], pnl_spark: [] },
  },
  meta: {
    connected: false,
    connection_event: "waiting",
    reconnects: 0,
    last_tick_age_sec: null,
    controls: {
      trading_enabled: true,
      kill_switch: false,
      strategies: { mean_reversion: true, momentum: true, volatility_breakout: true },
      risk: {
        confidence_threshold: 0.6,
        max_position_size: 0.1,
        max_daily_loss: 500,
        risk_per_trade: 0.01,
        daily_loss_limit: 500,
        max_exposure: 1,
        max_concurrent_positions: 1,
        cooldown_seconds: 5,
      },
    },
  },
  thought_stream: [],
  history: [],
  why_not_trade: [],
  strategy_intelligence: [],
  decision_inspector: { full_object: {}, features: {}, risk_checks: [], reasoning: "--" },
  counterfactuals: [],
  performance: { win_rate: 0, avg_profit: 0, max_drawdown: 0, sharpe_approx: 0, equity_curve: [] },
  replay: { cursor: 0, length: 0, timeline: [] },
  alerts: [],
  risk_state: {
    halted: false,
    kill_switch: false,
    trading_enabled: true,
    confidence_threshold: 0.6,
    max_position_size: 0.1,
    daily_loss_limit: 500,
    risk_per_trade: 0.01,
    max_exposure: 1,
    cooldown_seconds: 5,
    portfolio_drawdown_limit: 0.12,
    latest_risk_type: "",
    latest_risk_reason: "",
    latest_risk_severity: "info",
  },
};

export function useDecisionStream() {
  const [payload, setPayload] = useState<DecisionPayload>(fallback);
  const [debugMode, setDebugMode] = useState(false);
  const [filter, setFilter] = useState<"all" | "executed" | "blocked">("all");
  const [logFilter, setLogFilter] = useState<"all" | "errors" | "strategies" | "blocked">("all");
  const [riskFilter, setRiskFilter] = useState<"all" | "failed" | "executed">("all");
  const [selectedDecisionIndex, setSelectedDecisionIndex] = useState<number | null>(null);
  const [replayMode, setReplayMode] = useState(false);
  const [replayCursor, setReplayCursor] = useState(0);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [controlError, setControlError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);

  useEffect(() => {
    let mounted = true;

    const pullSnapshot = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/decision/snapshot`, { cache: "no-store" });
        if (!response.ok) return;
        const json = (await response.json()) as DecisionPayload;
        if (mounted) setPayload(json);
      } catch {
        // no-op, websocket or next poll will refresh
      }
    };

    pullSnapshot();

    const connect = () => {
      const ws = new WebSocket(WS_BASE);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const nextPayload = JSON.parse(event.data) as DecisionPayload;
          if (mounted) setPayload(nextPayload);
        } catch {
          // ignore malformed payload
        }
      };

      ws.onclose = () => {
        if (!mounted) return;
        reconnectAttemptRef.current += 1;
        const expBackoff = Math.min(10000, 1000 * (2 ** Math.min(reconnectAttemptRef.current, 4)));
        const jitter = Math.floor(Math.random() * 250);
        window.setTimeout(connect, expBackoff + jitter);
      };

      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      mounted = false;
      wsRef.current?.close();
    };
  }, []);

  const filteredHistory = useMemo(() => {
    if (filter === "all") return payload.history;
    if (filter === "executed") return payload.history.filter((row) => row.action === "EXECUTED");
    return payload.history.filter((row) => row.action === "BLOCKED");
  }, [payload.history, filter]);

  const filteredThoughtStream = useMemo(() => {
    if (logFilter === "all") return payload.thought_stream;
    if (logFilter === "errors") return payload.thought_stream.filter((row) => row.level === "error");
    if (logFilter === "strategies") {
      return payload.thought_stream.filter((row) =>
        /mean|momentum|volatility|breakout|strategy/i.test(row.stage + row.message)
      );
    }
    return payload.thought_stream.filter((row) => /blocked|risk/i.test(row.stage + row.message));
  }, [payload.thought_stream, logFilter]);

  const filteredRiskChecks = useMemo(() => {
    if (riskFilter === "all") return payload.why_not_trade;
    if (riskFilter === "failed") return payload.why_not_trade.filter((row) => row.checks.some((check) => !check.passed));
    return payload.why_not_trade.filter((row) => row.action === "EXECUTED");
  }, [payload.why_not_trade, riskFilter]);

  useEffect(() => {
    if (!payload.replay.timeline.length) return;
    if (!replayMode) {
      setReplayCursor(Math.max(payload.replay.timeline.length - 1, 0));
      return;
    }
    setReplayCursor((prev) => Math.min(prev, payload.replay.timeline.length - 1));
  }, [payload.replay.timeline, payload.replay.length, replayMode]);

  useEffect(() => {
    if (!replayMode || !replayPlaying) return;
    const id = window.setInterval(() => {
      setReplayCursor((cursor) => {
        const next = cursor + 1;
        if (next >= payload.replay.timeline.length) {
          setReplayPlaying(false);
          return cursor;
        }
        return next;
      });
    }, 900);
    return () => window.clearInterval(id);
  }, [replayMode, replayPlaying, payload.replay.timeline.length]);

  const activeHistory = replayMode ? payload.replay.timeline.slice(0, replayCursor + 1) : filteredHistory;

  const selectedDecision = useMemo(() => {
    if (selectedDecisionIndex === null) return null;
    if (selectedDecisionIndex < 0 || selectedDecisionIndex >= activeHistory.length) return null;
    return activeHistory[selectedDecisionIndex];
  }, [selectedDecisionIndex, activeHistory]);

  const postControl = async (path: string, body: object) => {
    try {
      setControlError(null);
      const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error(`Control request failed: ${response.status}`);
      }
      const json = (await response.json()) as { control?: DecisionPayload["meta"]["controls"] };
      if (json.control) {
        setPayload((prev) => ({
          ...prev,
          meta: {
            ...prev.meta,
            controls: json.control ?? prev.meta.controls,
          },
        }));
      }
      return json;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Control request failed";
      setControlError(message);
      return null;
    }
  };

  const setTradingEnabled = async (enabled: boolean) => postControl("/api/control/trading", { enabled });
  const setKillSwitch = async (engage: boolean) => postControl("/api/control/kill-switch", { engage });
  const setStrategyEnabled = async (strategy: string, enabled: boolean) => postControl("/api/control/strategy", { strategy, enabled });
  const updateRisk = async (risk: Partial<RiskControls>) =>
    postControl("/api/control/risk", risk);

  const replayStep = (delta: number) => {
    setReplayCursor((cursor) => Math.min(Math.max(cursor + delta, 0), Math.max(payload.replay.timeline.length - 1, 0)));
  };

  return {
    payload,
    debugMode,
    setDebugMode,
    filter,
    setFilter,
    filteredHistory,
    filteredThoughtStream,
    logFilter,
    setLogFilter,
    filteredRiskChecks,
    riskFilter,
    setRiskFilter,
    selectedDecision,
    selectedDecisionIndex,
    setSelectedDecisionIndex,
    activeHistory,
    replayMode,
    setReplayMode,
    replayCursor,
    replayPlaying,
    setReplayPlaying,
    replayStep,
    controlError,
    clearControlError: () => setControlError(null),
    setTradingEnabled,
    setKillSwitch,
    setStrategyEnabled,
    updateRisk,
  };
}
