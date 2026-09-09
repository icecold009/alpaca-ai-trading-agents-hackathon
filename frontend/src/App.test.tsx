import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";

describe("RiskCourt personal workstation", () => {
  it("renders the command center with truthful recorded-mode context", () => {
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "RiskCourt" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Good morning, operator." }),
    ).toBeInTheDocument();
    expect(screen.getByText("Recorded mode")).toBeInTheDocument();
    expect(screen.getByText("No credentials required")).toBeInTheDocument();
    expect(screen.getByText("SPY jury edge clears a 600/605 call spread")).toBeInTheDocument();
    expect(screen.getByText("Trade less.")).toBeInTheDocument();
  });

  it("navigates to the decision pipeline and exercises replay states", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Opportunities/ }));
    expect(
      screen.getByRole("heading", { level: 2, name: "Find the next defensible setup." }),
    ).toBeInTheDocument();
    expect(screen.getByText("Jury odds vs. market hurdle")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Market closed" }));
    expect(screen.getByText("Market closed — no order sent")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Provider failure" }));
    expect(screen.getByText("Provider unavailable — abstain")).toBeInTheDocument();
  });

  it("prepares an explicit approval and keeps recorded submission blocked", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Opportunities/ }));
    await user.click(screen.getByRole("button", { name: "Approve for paper order" }));
    expect(screen.getByText(/Approval ready · 1 contract/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Paper mode required" })).toBeDisabled();
  });

  it("keeps vetoes and journal notes local when the API is unavailable", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Opportunities/ }));
    await user.click(screen.getByRole("button", { name: /SPY jury cannot clear/i }));
    await user.click(screen.getByRole("button", { name: "Confirm veto" }));
    expect(
      screen.getByText("Decision vetoed. No order can follow this record."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Journal" }));
    await user.type(
      screen.getByPlaceholderText(/Capture the thesis/i),
      "Keep the edge threshold conservative.",
    );
    await user.click(screen.getByRole("button", { name: "Save note" }));
    expect(await screen.findByText("Keep the edge threshold conservative.")).toBeInTheDocument();
  });

  it("toggles the local kill switch from settings", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(screen.getByRole("button", { name: "Pause new entries" }));
    expect(screen.getByText("Enabled")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume new entries" })).toBeInTheDocument();
  });
});
