import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CommandBar from "@/components/CommandBar";

describe("CommandBar", () => {
  it("renders the input and Go button", () => {
    render(<CommandBar onSubmit={vi.fn()} />);
    expect(screen.getByPlaceholderText("Type command:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /go/i })).toBeInTheDocument();
  });

  it("calls onSubmit with the typed command on form submit", async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn();
    render(<CommandBar onSubmit={handleSubmit} />);

    await user.type(screen.getByPlaceholderText("Type command:"), "qt");
    await user.click(screen.getByRole("button", { name: /go/i }));

    expect(handleSubmit).toHaveBeenCalledOnce();
    expect(handleSubmit).toHaveBeenCalledWith("qt");
  });

  it("clears the input after submit", async () => {
    const user = userEvent.setup();
    render(<CommandBar onSubmit={vi.fn()} />);
    const input = screen.getByPlaceholderText("Type command:");

    await user.type(input, "drugs");
    await user.click(screen.getByRole("button", { name: /go/i }));

    expect(input).toHaveValue("");
  });

  it("submits on Enter key press", async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn();
    render(<CommandBar onSubmit={handleSubmit} />);

    await user.type(screen.getByPlaceholderText("Type command:"), "home{Enter}");

    expect(handleSubmit).toHaveBeenCalledWith("home");
  });
});
