import { describe, expect, it, vi } from "vitest";

import { loadRecordedCases, runtimeApiBaseUrl } from "./runtime";

describe("optional hosted runtime", () => {
  it("keeps the recorded fallback when no API base is configured", async () => {
    expect(runtimeApiBaseUrl(" ")).toBeNull();
    expect(await loadRecordedCases(vi.fn(), null)).toBeNull();
  });

  it("normalizes only absolute HTTP API origins", () => {
    expect(runtimeApiBaseUrl(" https://api.example/// ")).toBe("https://api.example");
    expect(runtimeApiBaseUrl("api.example")).toBeNull();
    expect(runtimeApiBaseUrl("ftp://api.example")).toBeNull();
  });

  it("loads validated case payloads from the API when available", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify([{ case_id: "case_edge_positive" }]), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            case_id: "case_edge_positive",
            name: "Edge",
            underlying_symbol: "SPY",
            as_of: "2026-08-30T15:00:00Z",
            forecasts: [
              {
                forecast_id: "forecast-1",
                juror_id: "juror_market",
                probability: "0.60",
                calibration_score: "0.90",
                confidence_stake: "0.80",
                evidence_ids: ["evidence-1"],
                rationale: "Recorded rationale",
              },
            ],
            strategy: {
              jury_probability: "0.60",
              market_hurdle: "0.55",
              probability_edge: "0.05",
              minimum_edge: "0.03",
              net_debit: "1.00",
              spread_width: "5.00",
            },
            intent: {
              maximum_loss: "100.00",
              direction: "bullish",
              legs: [
                {
                  occ_symbol: "SPY260830C00600000",
                  position_intent: "buy_to_open",
                  quantity: 1,
                  strike: "600.00",
                },
              ],
            },
            verdict: {
              decision: "approve",
              approved_quantity: 1,
              maximum_loss: "100.00",
              reasons: ["Edge clears hurdle"],
            },
            approval: null,
            executions: [],
            pnl_snapshots: [],
          }),
          { status: 200 },
        ),
      );

    const result = await loadRecordedCases(fetcher, runtimeApiBaseUrl("https://api.example/"));

    expect(result).toEqual([
      expect.objectContaining({ case_id: "case_edge_positive", underlying_symbol: "SPY" }),
    ]);
    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "https://api.example/api/recorded-cases",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("falls back when a hosted case payload is malformed", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify([{ case_id: "case_edge_positive" }])))
      .mockResolvedValueOnce(new Response(JSON.stringify({ case_id: "missing-fields" })));

    expect(await loadRecordedCases(fetcher, "https://api.example")).toBeNull();
  });

  it("rejects duplicate case summaries before requesting case details", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify([{ case_id: "case_edge_positive" }, { case_id: "case_edge_positive" }]),
          { status: 200 },
        ),
      );

    expect(await loadRecordedCases(fetcher, "https://api.example")).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
