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
    expect(
      screen.getByText("TypeSafe explains; deterministic RiskCourt decides."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Market closed" }));
    expect(screen.getByText("Market closed — no order sent")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Provider failure" }));
    expect(screen.getByText("Provider unavailable — abstain")).toBeInTheDocument();
  });

  it("keeps fixture approvals read-only until a backend decision exists", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Opportunities/ }));
    expect(screen.getByRole("button", { name: "Fixture is read-only" })).toBeDisabled();
    expect(screen.queryByText(/Approval ready/i)).not.toBeInTheDocument();
  });

  it("keeps fixture veto read-only and retains journal text when the API is unavailable", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Opportunities/ }));
    await user.click(screen.getByRole("button", { name: /SPY jury cannot clear/i }));
    expect(screen.getByRole("button", { name: "Fixture is read-only" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Journal" }));
    await user.type(
      screen.getByPlaceholderText(/Capture the thesis/i),
      "Keep the edge threshold conservative.",
    );
    await user.click(screen.getByRole("button", { name: "Save note" }));
    expect(screen.getByPlaceholderText(/Capture the thesis/i)).toHaveValue(
      "Keep the edge threshold conservative.",
    );
    expect(await screen.findByText(/not saved/i)).toBeInTheDocument();
  });

  it("shows an unknown kill switch when no backend state is available", async () => {
    render(<App />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Kill switch unknown" })).toBeDisabled();
  });
});
