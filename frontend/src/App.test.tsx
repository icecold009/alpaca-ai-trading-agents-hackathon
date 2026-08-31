import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";

describe("RiskCourt recorded cases", () => {
  it("renders the edge-positive decision card", () => {
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "RiskCourt" })).toBeInTheDocument();
    expect(screen.getByText("57.4%")).toBeInTheDocument();
    expect(screen.getByText("32.0%")).toBeInTheDocument();
    expect(screen.getByText("+$25.00")).toBeInTheDocument();
    expect(screen.getByText(/Approved after deterministic resize/i)).toBeInTheDocument();
    expect(screen.getByText("Option-implied hurdle")).toBeInTheDocument();
    expect(screen.getByText("Probability edge margin")).toBeInTheDocument();
    expect(screen.getAllByText("Calibration")).toHaveLength(3);
    expect(screen.getByText(/Minimum edge required:/)).toBeInTheDocument();
    expect(screen.getByText("Private reference redacted")).toBeInTheDocument();
    expect(screen.queryByText("riskcourt-case-edge-positive-v1")).not.toBeInTheDocument();
  });

  it("switches to the veto and back without fetching data", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /SPY jury cannot clear/i }));

    expect(screen.getByText("Verdict: veto")).toBeInTheDocument();
    expect(screen.getByText(/Trade vetoed — no order sent/i)).toBeInTheDocument();
    expect(screen.getByText(/No approval artifact/i)).toBeInTheDocument();
    expect(screen.getByText("-1.8 pp")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /SPY jury edge clears/i }));
    expect(screen.getByText("Verdict: resize")).toBeInTheDocument();
  });

  it("keeps the recorded-mode and financial disclaimers visible", () => {
    render(<App />);

    expect(screen.getByText(/Recorded mode · no credentials required/i)).toBeInTheDocument();
    expect(screen.getByText(/does not provide investment advice/i)).toBeInTheDocument();
  });

  it("replays blocked and failed safety states without leaving the page", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Market closed" }));
    expect(screen.getByRole("status")).toHaveTextContent("Market closed — no order sent");

    await user.click(screen.getByRole("button", { name: "Provider failure" }));
    expect(screen.getByRole("status")).toHaveTextContent("Provider unavailable — abstain");

    await user.click(screen.getByRole("button", { name: "Kill switch" }));
    expect(screen.getByRole("status")).toHaveTextContent("Kill switch active — execution disabled");
  });

  it("keeps safety state controls keyboard reachable", async () => {
    const user = userEvent.setup();
    render(<App />);

    const providerFailure = screen.getByRole("button", { name: "Provider failure" });
    providerFailure.focus();
    await user.keyboard("{Enter}");

    expect(providerFailure).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Provider unavailable — abstain");
  });
});
