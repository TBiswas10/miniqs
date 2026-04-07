from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import parse_qs, urlparse

from alpaca_config import AlpacaConfig


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_EVENTS = 200


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Alpaca Brain Trace</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

    :root {
      --bg: #070b10;
      --bg-2: #0b121b;
      --panel: rgba(14, 22, 32, 0.72);
      --panel-strong: rgba(17, 28, 40, 0.92);
      --line: rgba(255, 255, 255, 0.08);
      --text: #e8efe7;
      --muted: #8c9aa8;
      --accent: #9ddfca;
      --accent-2: #f0bf6b;
      --danger: #ff7a7a;
      --ok: #6bf0b6;
      --shadow: 0 26px 70px rgba(0, 0, 0, 0.35);
      --mono: 'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace;
      --serif: 'Cormorant Garamond', 'Iowan Old Style', 'Palatino Linotype', Georgia, serif;
    }

    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; background: var(--bg); color: var(--text); }
    body {
      font-family: var(--mono);
      background:
        radial-gradient(circle at top left, rgba(157, 223, 202, 0.14), transparent 28%),
        radial-gradient(circle at 80% 20%, rgba(240, 191, 107, 0.10), transparent 24%),
        radial-gradient(circle at 50% 100%, rgba(92, 122, 255, 0.10), transparent 22%),
        linear-gradient(180deg, #06090d 0%, #0a1017 50%, #06090d 100%);
      overflow-x: hidden;
    }

    .grain::before {
      content: '';
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.12;
      mix-blend-mode: soft-light;
      background-image:
        linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
      background-size: 42px 42px;
    }

    .wrap {
      max-width: 1680px;
      margin: 0 auto;
      padding: 28px;
    }

    .hero {
      position: relative;
      display: grid;
      grid-template-columns: 1.25fr 0.95fr;
      gap: 18px;
      padding: 22px;
      border: 1px solid var(--line);
      border-radius: 28px;
      background: linear-gradient(180deg, rgba(13, 19, 29, 0.9), rgba(9, 14, 22, 0.76));
      box-shadow: var(--shadow);
      overflow: hidden;
      animation: reveal 800ms ease both;
    }

    .hero::after {
      content: '';
      position: absolute;
      inset: auto -10% -40% auto;
      width: 420px;
      height: 420px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(157, 223, 202, 0.16), transparent 65%);
      filter: blur(4px);
      animation: drift 14s ease-in-out infinite alternate;
    }

    .eyebrow {
      font-size: 12px;
      letter-spacing: 0.32em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 14px;
    }

    h1 {
      font-family: var(--serif);
      font-size: clamp(44px, 6vw, 88px);
      line-height: 0.92;
      margin: 0;
      font-weight: 700;
      letter-spacing: -0.03em;
    }

    .subtitle {
      margin: 18px 0 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.8;
      max-width: 62ch;
    }

    .hero-right {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      align-content: start;
      z-index: 1;
    }

    .hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 22px;
      align-items: center;
    }

    .reason-banner {
      margin-top: 14px;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid rgba(157, 223, 202, 0.22);
      background: linear-gradient(180deg, rgba(157, 223, 202, 0.08), rgba(17, 24, 34, 0.78));
      color: #d8efe6;
      font-size: 12px;
      line-height: 1.6;
    }

    .ops-grid {
      margin-top: 12px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .mini-panel {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.03);
    }

    .mini-panel .k {
      color: var(--muted);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      margin-bottom: 8px;
    }

    .mini-row {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      font-size: 12px;
      line-height: 1.5;
      margin-bottom: 4px;
    }

    .mini-row span:last-child {
      color: var(--text);
      font-weight: 600;
    }

    .mini-row .warn {
      color: var(--danger);
    }

    .mini-row .ok {
      color: var(--ok);
    }

    .mini-row:last-child {
      margin-bottom: 0;
    }

    .flow-shell {
      margin-top: 18px;
      padding: 16px;
      border-radius: 22px;
      border: 1px solid var(--line);
      background:
        radial-gradient(circle at 10% 0%, rgba(157, 223, 202, 0.12), transparent 30%),
        linear-gradient(180deg, rgba(9, 15, 23, 0.92), rgba(7, 11, 16, 0.94));
      position: relative;
      overflow: hidden;
    }

    .flow-shell::before {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(105deg, transparent 0%, rgba(157, 223, 202, 0.06) 50%, transparent 100%);
      transform: translateX(-35%);
      animation: sweep 9s linear infinite;
      pointer-events: none;
    }

    .flow-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
      position: relative;
      z-index: 1;
    }

    .flow-title {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.28em;
      color: var(--muted);
    }

    .flow-status {
      font-size: 11px;
      color: var(--accent);
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }

    .flow-track {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
      position: relative;
      z-index: 1;
    }

    .flow-track::before {
      content: '';
      position: absolute;
      left: 7%;
      right: 7%;
      top: 36px;
      height: 2px;
      background: linear-gradient(90deg, rgba(157, 223, 202, 0.08), rgba(157, 223, 202, 0.5), rgba(240, 191, 107, 0.35), rgba(157, 223, 202, 0.08));
      filter: blur(0.2px);
      opacity: 0.95;
    }

    .flow-node {
      position: relative;
      min-height: 92px;
      padding: 14px 10px 12px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(18, 27, 38, 0.96), rgba(11, 16, 23, 0.92));
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      gap: 6px;
      text-align: center;
      transition: transform 260ms ease, border-color 260ms ease, background 260ms ease, box-shadow 260ms ease;
    }

    .flow-node::after {
      content: '';
      position: absolute;
      inset: -1px;
      border-radius: inherit;
      background: radial-gradient(circle at 50% 0%, rgba(157,223,202,0.22), transparent 60%);
      opacity: 0;
      transition: opacity 260ms ease;
    }

    .flow-node[data-done="true"] {
      border-color: rgba(157, 223, 202, 0.34);
      box-shadow: inset 0 0 0 1px rgba(157, 223, 202, 0.08);
    }

    .flow-node[data-active="true"] {
      transform: translateY(-6px) scale(1.02);
      border-color: rgba(157, 223, 202, 0.78);
      box-shadow: 0 0 0 1px rgba(157, 223, 202, 0.24), 0 18px 34px rgba(0, 0, 0, 0.28);
    }

    .flow-node[data-active="true"]::after {
      opacity: 1;
    }

    .flow-index {
      width: 28px;
      height: 28px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      font-size: 10px;
      color: #03120d;
      font-weight: 700;
      background: linear-gradient(180deg, var(--accent), rgba(157, 223, 202, 0.72));
      box-shadow: 0 0 0 6px rgba(157, 223, 202, 0.08);
      position: relative;
      z-index: 1;
    }

    .flow-node .flow-label {
      font-size: 10px;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--text);
      position: relative;
      z-index: 1;
    }

    .flow-node .flow-desc {
      font-size: 10px;
      line-height: 1.4;
      color: var(--muted);
      position: relative;
      z-index: 1;
    }

    .chip, .stat, .card, .panel {
      border: 1px solid var(--line);
      background: var(--panel);
      backdrop-filter: blur(14px);
      box-shadow: 0 18px 45px rgba(0, 0, 0, 0.22);
    }

    .chip {
      border-radius: 18px;
      padding: 14px 16px;
      min-height: 90px;
    }

    .chip .label, .stat .label, .section-label {
      text-transform: uppercase;
      letter-spacing: 0.22em;
      font-size: 10px;
      color: var(--muted);
      margin-bottom: 10px;
    }

    .chip .value, .stat .value {
      font-size: 24px;
      line-height: 1.1;
      font-weight: 600;
      color: var(--text);
    }

    .chip .note, .stat .note {
      margin-top: 8px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.5;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.04);
      font-size: 11px;
      color: var(--muted);
    }

    .badge .dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--accent);
      box-shadow: 0 0 0 6px rgba(157, 223, 202, 0.1);
    }

    .grid {
      margin-top: 18px;
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 18px;
    }

    .panel {
      border-radius: 24px;
      padding: 18px;
      min-height: 320px;
    }

    .panel-header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }

    .panel-title {
      font-family: var(--serif);
      font-size: 32px;
      margin: 0;
      letter-spacing: -0.02em;
    }

    .panel-subtitle {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 12px;
    }

    .trace-list {
      display: grid;
      gap: 12px;
    }

    .trace-card {
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(17, 27, 39, 0.92), rgba(11, 17, 25, 0.82));
      border-radius: 20px;
      padding: 14px 15px;
      position: relative;
      overflow: hidden;
      animation: slideUp var(--trace-duration, 450ms) ease both;
      animation-delay: calc(var(--trace-index, 0) * var(--trace-stagger, 70ms));
    }

    .trace-card::before {
      content: '';
      position: absolute;
      inset: 0 auto 0 0;
      width: 4px;
      background: var(--accent);
    }

    .trace-card[data-kind="connection"]::before { background: var(--accent-2); }
    .trace-card[data-kind="trade_update"]::before { background: var(--ok); }
    .trace-card[data-stage="risk_blocked"]::before { background: var(--danger); }

    .trace-meta {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 11px;
      margin-bottom: 8px;
    }

    .trace-stage {
      color: var(--text);
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 10px;
    }

    .trace-body {
      color: #cfd8e4;
      font-size: 12px;
      line-height: 1.7;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .decision-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .stat {
      border-radius: 20px;
      padding: 15px;
      min-height: 116px;
    }

    .stat .value.small { font-size: 18px; }

    .spark {
      margin-top: 14px;
      width: 100%;
      height: 120px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
      position: relative;
      overflow: hidden;
    }

    .confidence-spark {
      margin-top: 10px;
      height: 92px;
    }

    .spark svg {
      width: 100%;
      height: 100%;
      display: block;
    }

    .spark .spark-label {
      position: absolute;
      top: 12px;
      left: 14px;
      font-size: 11px;
      color: var(--muted);
      letter-spacing: 0.2em;
      text-transform: uppercase;
      z-index: 1;
    }

    .signal-panel {
      display: grid;
      gap: 12px;
    }

    .signal-row {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px 13px;
      background: rgba(255,255,255,0.03);
    }

    .signal-row .k {
      color: var(--muted);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      margin-bottom: 6px;
    }

    .signal-row .v {
      font-size: 14px;
      line-height: 1.6;
      white-space: pre-wrap;
    }

    .footer-bar {
      margin-top: 18px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: space-between;
      color: var(--muted);
      font-size: 11px;
    }

    .glow {
      text-shadow: 0 0 20px rgba(157, 223, 202, 0.2);
    }

    .pulse {
      animation: pulse 1.8s ease-in-out infinite;
    }

    @keyframes reveal {
      from { opacity: 0; transform: translateY(18px) scale(0.985); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    @keyframes slideUp {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @keyframes drift {
      from { transform: translate(0, 0) scale(1); }
      to { transform: translate(-18px, 16px) scale(1.05); }
    }

    @keyframes sweep {
      from { transform: translateX(-40%); }
      to { transform: translateX(40%); }
    }

    @keyframes pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(157, 223, 202, 0.16); }
      50% { box-shadow: 0 0 0 10px rgba(157, 223, 202, 0); }
    }

    @media (max-width: 1100px) {
      .hero, .grid { grid-template-columns: 1fr; }
      .hero-right, .decision-grid { grid-template-columns: 1fr; }
      .panel-title { font-size: 26px; }
    }
  </style>
</head>
<body>
  <div class="grain"></div>
  <div class="wrap">
    <section class="hero">
      <div>
        <div class="eyebrow">Alpaca Paper Trading Brain Trace</div>
        <h1 class="glow">Live decision stream<br/>from the trading loop.</h1>
        <p class="subtitle">
          Watch the bot think in real time: price intake, feature warmup, signal generation, confidence filtering,
          risk rejection, and paper order execution. This dashboard polls the trace log and renders the current state
          as a control-room style observatory.
        </p>
        <div class="hero-actions">
          <div class="badge"><span class="dot pulse"></span><span id="speed-label">live monitoring</span></div>
        </div>
        <div class="reason-banner" id="decision-reason">Waiting for live trace.</div>
        <div class="flow-shell">
          <div class="flow-header">
            <div class="flow-title">Execution flow</div>
            <div class="flow-status" id="flow-status">waiting for trace</div>
          </div>
          <div class="flow-track" id="flow-track">
            <div class="flow-node" data-stage="market_data_tick">
              <div class="flow-index">01</div>
              <div class="flow-label">Market data</div>
              <div class="flow-desc">stream ticks and prices</div>
            </div>
            <div class="flow-node" data-stage="warmup">
              <div class="flow-index">02</div>
              <div class="flow-label">Features</div>
              <div class="flow-desc">rolling windows and momentum</div>
            </div>
            <div class="flow-node" data-stage="signals_generated">
              <div class="flow-index">03</div>
              <div class="flow-label">Signals</div>
              <div class="flow-desc">mean reversion and momentum</div>
            </div>
            <div class="flow-node" data-stage="risk_check">
              <div class="flow-index">04</div>
              <div class="flow-label">Risk gate</div>
              <div class="flow-desc">cooldown, position, loss checks</div>
            </div>
            <div class="flow-node" data-stage="trade_submission">
              <div class="flow-index">05</div>
              <div class="flow-label">Execution</div>
              <div class="flow-desc">submit paper order and wait</div>
            </div>
            <div class="flow-node" data-stage="trade_executed">
              <div class="flow-index">06</div>
              <div class="flow-label">Dashboard</div>
              <div class="flow-desc">metrics, trace, and portfolio</div>
            </div>
          </div>
        </div>
      </div>
      <div class="hero-right" id="status-chips">
        <div class="chip"><div class="label">Connection</div><div class="value">Waiting...</div><div class="note">data and trade streams</div></div>
        <div class="chip"><div class="label">Stage</div><div class="value">Idle</div><div class="note">current loop state</div></div>
        <div class="chip"><div class="label">Trades</div><div class="value">0</div><div class="note">executed paper orders</div></div>
        <div class="chip"><div class="label">Symbol</div><div class="value">--</div><div class="note">primary execution symbol</div></div>
      </div>
    </section>

    <div class="grid">
      <section class="panel">
        <div class="panel-header">
          <div>
            <div class="section-label">Decision Pipeline</div>
            <h2 class="panel-title">Brain trace timeline</h2>
            <div class="panel-subtitle">Recent connection events and trade decisions from the live runner.</div>
          </div>
          <div class="badge"><span class="dot pulse"></span><span id="last-updated">polling</span></div>
        </div>
        <div class="trace-list" id="trace-list"></div>
      </section>

      <section class="panel signal-panel">
        <div class="panel-header">
          <div>
            <div class="section-label">Decision Table</div>
            <h2 class="panel-title">Current snapshot</h2>
            <div class="panel-subtitle">The latest signal, risk, and portfolio state from the live trace.</div>
          </div>
        </div>

        <div class="decision-grid" id="stats-grid">
          <div class="stat"><div class="label">Equity</div><div class="value">--</div><div class="note">mark-to-market value</div></div>
          <div class="stat"><div class="label">PnL</div><div class="value">--</div><div class="note">realized + unrealized minus fees</div></div>
          <div class="stat"><div class="label">Confidence</div><div class="value">--</div><div class="note">best chosen signal</div></div>
          <div class="stat"><div class="label">Risk</div><div class="value">--</div><div class="note">last risk gate result</div></div>
        </div>

        <div class="spark">
          <div class="spark-label">Price path</div>
          <svg id="sparkline" viewBox="0 0 800 120" preserveAspectRatio="none"></svg>
        </div>

        <div class="spark confidence-spark">
          <div class="spark-label">Confidence path</div>
          <svg id="confline" viewBox="0 0 800 120" preserveAspectRatio="none"></svg>
        </div>

        <div class="signal-row">
          <div class="k">Mean reversion</div>
          <div class="v" id="mr-signal">--</div>
        </div>
        <div class="signal-row">
          <div class="k">Momentum</div>
          <div class="v" id="mo-signal">--</div>
        </div>
        <div class="signal-row">
          <div class="k">Chosen action</div>
          <div class="v" id="chosen-signal">--</div>
        </div>
        <div class="signal-row">
          <div class="k">Risk reason</div>
          <div class="v" id="risk-reason">--</div>
        </div>

        <div class="ops-grid">
          <div class="mini-panel">
            <div class="k">Stream health</div>
            <div class="mini-row"><span>Last tick age</span><span id="health-tick-age">--</span></div>
            <div class="mini-row"><span>Reconnects</span><span id="health-reconnects">0</span></div>
            <div class="mini-row"><span>Auth failures</span><span id="health-auth" class="warn">0</span></div>
          </div>
          <div class="mini-panel">
            <div class="k">Risk scoreboard</div>
            <div class="mini-row"><span>Allowed</span><span id="risk-allowed" class="ok">0</span></div>
            <div class="mini-row"><span>Cooldown blocks</span><span id="risk-cooldown">0</span></div>
            <div class="mini-row"><span>Position/loss/other</span><span id="risk-other">0</span></div>
          </div>
        </div>
      </section>
    </div>

    <div class="footer-bar">
      <div>Local dashboard: <span class="glow">http://127.0.0.1:8765</span></div>
      <div>Trace file: <span class="glow">logs/alpaca_brain_trace.jsonl</span></div>
      <div>Refresh interval: <span class="glow">2s</span></div>
    </div>
  </div>

  <script>
    const stateUrl = '/api/state';
    const flowOrder = [
      'market_data_tick',
      'warmup',
      'signals_generated',
      'no_signal',
      'risk_check',
      'risk_blocked',
      'trade_submission',
      'trade_executed',
    ];

    let refreshIntervalMs = 2000;
    let refreshTimer = null;

    function fmt(n, digits = 2) {
      const num = Number(n);
      if (!Number.isFinite(num)) return '--';
      return num.toFixed(digits);
    }

    function stageLabel(stage) {
      return String(stage || 'idle').replaceAll('_', ' ');
    }

    function stageRank(stage) {
      const value = String(stage || '').toLowerCase();
      const rank = flowOrder.indexOf(value);
      return rank >= 0 ? rank : -1;
    }

    function signalText(signal) {
      if (!signal) return '--';
      return `${signal.action} · ${fmt(signal.confidence, 3)} · ${signal.reason || ''}`.trim();
    }

    function ageText(seconds) {
      const value = Number(seconds);
      if (!Number.isFinite(value)) return '--';
      if (value < 1) return '<1s';
      if (value < 60) return `${Math.round(value)}s`;
      const mins = Math.floor(value / 60);
      const secs = Math.round(value % 60);
      return `${mins}m ${secs}s`;
    }

    function renderSparkline(points) {
      const svg = document.getElementById('sparkline');
      if (!points || !points.length) {
        svg.innerHTML = '';
        return;
      }
      const values = points.map(p => Number(p.price)).filter(Number.isFinite);
      if (!values.length) return;
      const min = Math.min(...values);
      const max = Math.max(...values);
      const w = 800;
      const h = 120;
      const pad = 10;
      const span = Math.max(max - min, 0.0001);
      const xStep = (w - pad * 2) / Math.max(values.length - 1, 1);
      const coords = values.map((v, i) => {
        const x = pad + i * xStep;
        const y = h - pad - ((v - min) / span) * (h - pad * 2);
        return `${x},${y}`;
      }).join(' ');
      svg.innerHTML = `
        <defs>
          <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#9ddfca"/>
            <stop offset="100%" stop-color="#f0bf6b"/>
          </linearGradient>
        </defs>
        <polyline fill="none" stroke="url(#lineGrad)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="${coords}" />
      `;
    }

    function renderConfidenceLine(points) {
      const svg = document.getElementById('confline');
      if (!svg) return;
      if (!points || !points.length) {
        svg.innerHTML = '';
        return;
      }
      const values = points.map(p => Number(p.confidence)).filter(v => Number.isFinite(v));
      if (!values.length) {
        svg.innerHTML = '';
        return;
      }
      const w = 800;
      const h = 120;
      const pad = 10;
      const xStep = (w - pad * 2) / Math.max(values.length - 1, 1);
      const coords = values.map((v, i) => {
        const x = pad + i * xStep;
        const y = h - pad - (Math.max(Math.min(v, 1), 0)) * (h - pad * 2);
        return `${x},${y}`;
      }).join(' ');
      const thresholdY = h - pad - (0.60 * (h - pad * 2));
      svg.innerHTML = `
        <defs>
          <linearGradient id="confGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#f0bf6b"/>
            <stop offset="100%" stop-color="#9ddfca"/>
          </linearGradient>
        </defs>
        <line x1="${pad}" y1="${thresholdY}" x2="${w - pad}" y2="${thresholdY}" stroke="rgba(255,122,122,0.45)" stroke-dasharray="6 6" />
        <polyline fill="none" stroke="url(#confGrad)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="${coords}" />
      `;
    }

    function renderFlow(stage) {
      const nodes = document.querySelectorAll('.flow-node');
      const rank = stageRank(stage);
      nodes.forEach((node, index) => {
        const isDone = rank >= index;
        const isActive = rank === index;
        node.dataset.done = isDone ? 'true' : 'false';
        node.dataset.active = isActive ? 'true' : 'false';
      });
      document.getElementById('flow-status').textContent = rank >= 0 ? stageLabel(stage) : 'waiting for trace';
    }

    function renderStats(summary) {
      const stats = document.querySelectorAll('#stats-grid .stat .value');
      if (stats[0]) stats[0].textContent = fmt(summary.equity, 2);
      if (stats[1]) stats[1].textContent = fmt(summary.total_pnl, 4);
      if (stats[2]) stats[2].textContent = summary.latest_confidence !== null && summary.latest_confidence !== undefined ? fmt(summary.latest_confidence, 3) : '--';
      if (stats[3]) stats[3].textContent = summary.latest_risk || '--';

      const chips = document.getElementById('status-chips').children;
      if (chips[0]) chips[0].querySelector('.value').textContent = summary.connection_state || 'Connected';
      if (chips[1]) chips[1].querySelector('.value').textContent = stageLabel(summary.stage);
      if (chips[2]) chips[2].querySelector('.value').textContent = String(summary.executed_trades ?? 0);
      if (chips[3]) chips[3].querySelector('.value').textContent = summary.symbol || '--';

      document.getElementById('mr-signal').textContent = signalText(summary.mean_reversion);
      document.getElementById('mo-signal').textContent = signalText(summary.momentum);
      document.getElementById('chosen-signal').textContent = summary.chosen ? `${summary.chosen.strategy} · ${summary.chosen.action} · ${fmt(summary.chosen.confidence, 3)} · ${summary.chosen.reason || ''}` : '--';
      document.getElementById('risk-reason').textContent = summary.risk ? (summary.risk.allowed ? 'allowed' : `blocked · ${summary.risk.reason || ''}`) : '--';
      document.getElementById('decision-reason').textContent = summary.decision_reason || 'Waiting for live trace.';
      document.getElementById('health-tick-age').textContent = ageText(summary.last_tick_age_seconds);
      document.getElementById('health-reconnects').textContent = String(summary.stream_reconnects ?? 0);
      document.getElementById('health-auth').textContent = String(summary.auth_failures ?? 0);
      const riskCounts = summary.risk_counts || {};
      document.getElementById('risk-allowed').textContent = String(riskCounts.allowed ?? 0);
      document.getElementById('risk-cooldown').textContent = String(riskCounts.cooldown ?? 0);
      const otherTotal = Number(riskCounts.position ?? 0) + Number(riskCounts.loss ?? 0) + Number(riskCounts.other ?? 0);
      document.getElementById('risk-other').textContent = String(otherTotal);
      renderFlow(summary.stage);
    }

    function renderTrace(events) {
      const list = document.getElementById('trace-list');
      if (!events.length) {
        list.innerHTML = '<div class="trace-card"><div class="trace-stage">Waiting for trace data</div><div class="trace-body">Start the runner and this dashboard will show the bot\'s internal decisions here.</div></div>';
        return;
      }
      list.innerHTML = events.slice().reverse().map((event, index) => {
        const details = [
          event.symbol ? `symbol=${event.symbol}` : null,
          Number.isFinite(Number(event.price)) ? `price=${fmt(event.price, 4)}` : null,
          event.decision ? `decision=${event.decision}` : null,
          event.trade && event.trade.status === 'executed' ? `trade=${event.trade.action}@${fmt(event.trade.price, 4)}` : null,
          event.risk ? `risk=${event.risk.allowed ? 'allowed' : event.risk.reason}` : null,
        ].filter(Boolean).join(' · ');
        const traceText = event.detail || 'Open event for full payload.';
        return `
          <article class="trace-card" data-kind="${event.kind || 'decision'}" data-stage="${event.stage || ''}" style="--trace-index:${index}">
            <div class="trace-meta">
              <span>${event.ts || event.timestamp || '--'}</span>
              <span>${event.tick ? `tick ${event.tick}` : ''}</span>
            </div>
            <div class="trace-stage">${stageLabel(event.stage || event.kind || 'event')}</div>
            <div class="trace-body">${details || '—'}\n\n${traceText}</div>
            <details style="margin-top:8px;">
              <summary style="cursor:pointer;color:var(--muted);font-size:11px;">raw payload</summary>
              <pre style="white-space:pre-wrap;color:#9fb0c0;font-size:11px;line-height:1.5;">${JSON.stringify(event, null, 2)}</pre>
            </details>
          </article>
        `;
      }).join('');
    }

    function restartPolling() {
      if (refreshTimer) clearInterval(refreshTimer);
      refreshTimer = setInterval(refresh, refreshIntervalMs);
    }

    async function refresh() {
      try {
        const response = await fetch(stateUrl, { cache: 'no-store' });
        const data = await response.json();
        const summary = data.summary || {};
        renderStats(summary);
        renderTrace(data.events || []);
        renderSparkline(data.price_points || []);
        renderConfidenceLine(data.confidence_points || []);
        document.getElementById('last-updated').textContent = `updated ${new Date().toLocaleTimeString()}`;
      } catch (error) {
        document.getElementById('last-updated').textContent = 'offline';
      }
    }

    restartPolling();
    refresh();
  </script>
</body>
</html>
"""


@dataclass
class DashboardConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    brain_trace_jsonl: str = "logs/alpaca_brain_trace.jsonl"
    live_dashboard_jsonl: str = "logs/live_dashboard.jsonl"
    dashboard_snapshot_json: str = "logs/live_dashboard_snapshot.json"


class BrainTraceStore:
    def __init__(self, cfg: DashboardConfig) -> None:
        self.cfg = cfg

    def _read_jsonl(self, path: str, limit: int = MAX_EVENTS) -> List[Dict[str, Any]]:
        file_path = Path(path)
        if not file_path.exists():
            return []
        items: List[Dict[str, Any]] = []
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return items[-limit:]

    def _read_json(self, path: str) -> Dict[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            return {}
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _parse_ts(self, value: Any) -> Optional[datetime]:
      if not isinstance(value, str) or not value:
        return None
      raw = value.strip()
      if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
      try:
        dt = datetime.fromisoformat(raw)
      except ValueError:
        return None
      if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
      return dt

    def load_state(self) -> Dict[str, Any]:
        events = self._read_jsonl(self.cfg.brain_trace_jsonl, MAX_EVENTS)
        dashboard_events = self._read_jsonl(self.cfg.live_dashboard_jsonl, 40)
        snapshot = self._read_json(self.cfg.dashboard_snapshot_json)
        latest_decision = next((event for event in reversed(events) if event.get("kind") == "decision"), None)
        latest_connection = next((event for event in reversed(events) if event.get("kind") == "connection"), None)
        latest_trade = next((event for event in reversed(events) if event.get("kind") == "trade_update"), None)

        summary: Dict[str, Any] = {
            "symbol": latest_decision.get("symbol") if latest_decision else snapshot.get("latest", {}).get("symbol", "BTC/USD"),
            "stage": latest_decision.get("stage") if latest_decision else (latest_connection.get("event") if latest_connection else "idle"),
            "equity": latest_decision.get("equity") if latest_decision else snapshot.get("latest", {}).get("equity", 0.0),
            "total_pnl": latest_decision.get("total_pnl") if latest_decision else snapshot.get("latest", {}).get("total_pnl", 0.0),
            "latest_confidence": None,
            "latest_risk": None,
            "connection_state": "connected" if latest_connection else "waiting",
          "decision_reason": "Waiting for live trace.",
          "last_tick_age_seconds": None,
          "stream_reconnects": 0,
          "auth_failures": 0,
          "risk_counts": {
            "allowed": 0,
            "cooldown": 0,
            "position": 0,
            "loss": 0,
            "other": 0,
          },
        }

        summary["stream_reconnects"] = sum(
          1
          for event in events
          if event.get("kind") == "connection" and "reconnect" in str(event.get("event", "")).lower()
        )
        summary["auth_failures"] = sum(
          1
          for event in events
          if event.get("kind") == "connection"
          and ("auth" in str(event.get("event", "")).lower() or "auth" in str(event.get("detail", "")).lower())
          and ("fail" in str(event.get("event", "")).lower() or "timeout" in str(event.get("detail", "")).lower())
        )

        decision_trade_counts = [
          int(event.get("executed_trades", 0))
          for event in events
          if event.get("kind") == "decision" and isinstance(event.get("executed_trades", 0), (int, float))
        ]
        summary["executed_trades"] = max(decision_trade_counts, default=snapshot.get("latest", {}).get("executed_trades", 0))

        if latest_decision:
            summary["price"] = latest_decision.get("price")
            if isinstance(latest_decision.get("chosen"), dict):
                summary["latest_confidence"] = latest_decision["chosen"].get("confidence")
            if isinstance(latest_decision.get("risk"), dict):
                summary["latest_risk"] = "allowed" if latest_decision["risk"].get("allowed") else latest_decision["risk"].get("reason")
            summary["mean_reversion"] = latest_decision.get("signals", {}).get("mean_reversion") if isinstance(latest_decision.get("signals"), dict) else None
            summary["momentum"] = latest_decision.get("signals", {}).get("momentum") if isinstance(latest_decision.get("signals"), dict) else None
            summary["chosen"] = latest_decision.get("chosen")
            summary["risk"] = latest_decision.get("risk")
            summary["trade"] = latest_decision.get("trade")
            summary["portfolio_after"] = latest_decision.get("portfolio_after")

            chosen = latest_decision.get("chosen")
            risk = latest_decision.get("risk")
            decision = latest_decision.get("decision")
            detail = latest_decision.get("detail")
            if isinstance(risk, dict) and risk.get("allowed") is False:
                summary["decision_reason"] = f"No trade: risk blocked ({risk.get('reason') or 'unknown reason'})."
            elif isinstance(chosen, dict):
                summary["decision_reason"] = (
                    f"{str(chosen.get('action', 'hold')).upper()} from {chosen.get('strategy', 'strategy')} "
                    f"at confidence {float(chosen.get('confidence', 0.0)):.3f}."
                )
            elif isinstance(decision, str) and decision.lower() == "warmup":
                summary["decision_reason"] = "Warming up feature windows before taking trades."
            elif isinstance(detail, str) and detail:
                summary["decision_reason"] = f"No trade: {detail.replace('_', ' ')}."

            ts_value = latest_decision.get("timestamp") or latest_decision.get("ts")
            tick_ts = self._parse_ts(ts_value)
            if tick_ts is not None:
                summary["last_tick_age_seconds"] = max((datetime.now(timezone.utc) - tick_ts).total_seconds(), 0.0)
        else:
            summary["mean_reversion"] = None
            summary["momentum"] = None
            summary["chosen"] = None
            summary["risk"] = None
            summary["trade"] = None
            summary["portfolio_after"] = None

        for event in events:
            if event.get("kind") != "decision":
                continue
            risk = event.get("risk")
            if not isinstance(risk, dict):
                continue
            if risk.get("allowed"):
                summary["risk_counts"]["allowed"] += 1
                continue
            reason = str(risk.get("reason", "")).lower()
            if "cooldown" in reason:
                summary["risk_counts"]["cooldown"] += 1
            elif "position" in reason:
                summary["risk_counts"]["position"] += 1
            elif "loss" in reason or "drawdown" in reason:
                summary["risk_counts"]["loss"] += 1
            else:
                summary["risk_counts"]["other"] += 1

        price_points = [
            {"price": event.get("price"), "tick": event.get("tick")}
            for event in events
            if event.get("kind") == "decision" and isinstance(event.get("price"), (int, float))
        ][-120:]

        confidence_points = []
        for event in events:
          if event.get("kind") != "decision":
            continue
          chosen = event.get("chosen") if isinstance(event.get("chosen"), dict) else None
          if chosen is not None:
            conf_value = float(chosen.get("confidence", 0.0) or 0.0)
          else:
            signals = event.get("signals") if isinstance(event.get("signals"), dict) else {}
            mr = signals.get("mean_reversion") if isinstance(signals.get("mean_reversion"), dict) else {}
            mo = signals.get("momentum") if isinstance(signals.get("momentum"), dict) else {}
            conf_value = max(
              float(mr.get("confidence", 0.0) or 0.0),
              float(mo.get("confidence", 0.0) or 0.0),
            )
          confidence_points.append({"confidence": conf_value, "tick": event.get("tick")})
        confidence_points = confidence_points[-120:]

        return {
            "summary": summary,
            "events": events[-40:],
            "price_points": price_points,
            "confidence_points": confidence_points,
            "snapshot": snapshot,
            "dashboard_events": dashboard_events,
            "latest_trade_update": latest_trade,
        }


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "AlpacaBrainDashboard/1.0"

    @property
    def store(self) -> BrainTraceStore:
        return self.server.store  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/state":
            self._send_json(self.store.load_state())
            return

        if parsed.path == "/api/health":
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/events":
            params = parse_qs(parsed.query)
            limit = int(params.get("limit", [40])[0])
            state = self.store.load_state()
            self._send_json({"events": state["events"][-limit:]})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "not found")


class BrainTraceHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], RequestHandlerClass: type[BaseHTTPRequestHandler], store: BrainTraceStore) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.store = store


def serve_dashboard(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    cfg = DashboardConfig(host=host, port=port)
    store = BrainTraceStore(cfg)
    server = BrainTraceHTTPServer((cfg.host, cfg.port), RequestHandler, store)
    print(f"[alpaca_dashboard] serving on http://{cfg.host}:{cfg.port}")
    print(f"[alpaca_dashboard] trace file: {cfg.brain_trace_jsonl}")
    print("[alpaca_dashboard] refresh the page to follow the live brain trace")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[alpaca_dashboard] stopped")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Alpaca brain-trace dashboard.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    args = parser.parse_args()
    serve_dashboard(args.host, args.port)


if __name__ == "__main__":
    main()
