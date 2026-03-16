import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthContext } from "@/context/AuthContext";
import LoginForm from "@/components/LoginForm";

// The label elements in LoginForm are not htmlFor-associated with their inputs,
// so we query by placeholder text, role, or input type instead of getByLabelText.

function makeAuthValue(overrides = {}) {
  return {
    login: vi.fn(),
    loginByCode: vi.fn(),
    timedOut: false,
    quickCode: null,
    clearQuickCode: vi.fn(),
    ...overrides,
  };
}

function renderLoginForm(authOverrides = {}, props = {}) {
  const value = makeAuthValue(authOverrides);
  const result = render(
    <AuthContext.Provider value={value}>
      <LoginForm {...props} />
    </AuthContext.Provider>
  );
  return { ...result, authValue: value };
}

describe("LoginForm", () => {
  it("renders the Quick Code tab by default with a code input", () => {
    renderLoginForm();
    // The quick-code input has placeholder "ABC"
    expect(screen.getByPlaceholderText("ABC")).toBeInTheDocument();
  });

  it("switches to the Sign In (credentials) tab", async () => {
    const user = userEvent.setup();
    renderLoginForm();

    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    // Credentials form has a text input (username) — password type is not role=textbox
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(document.querySelector('input[type="password"]')).toBeInTheDocument();
  });

  it("calls login with username and password on credentials submit", async () => {
    const user = userEvent.setup();
    const login = vi.fn().mockResolvedValue(undefined);
    renderLoginForm({ login });

    // Click the tab — after this, both the tab button AND form submit are labelled "Sign In"
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await user.type(screen.getByRole("textbox"), "alice");
    await user.type(document.querySelector('input[type="password"]'), "secret");

    // Use the submit button (type="submit") specifically to avoid the tab ambiguity
    const submitBtn = document.querySelector('button[type="submit"]');
    await user.click(submitBtn);

    await waitFor(() => expect(login).toHaveBeenCalledWith("alice", "secret"));
  });

  it("shows an error message when login fails", async () => {
    const user = userEvent.setup();
    const login = vi.fn().mockRejectedValue(new Error("bad creds"));
    renderLoginForm({ login });

    await user.click(screen.getByRole("button", { name: /^sign in$/i }));
    await user.type(screen.getByRole("textbox"), "baduser");
    await user.type(document.querySelector('input[type="password"]'), "wrong");

    const submitBtn = document.querySelector('button[type="submit"]');
    await user.click(submitBtn);

    await waitFor(() =>
      expect(screen.getByText(/invalid username or password/i)).toBeInTheDocument()
    );
  });

  it("shows the timed-out banner when timedOut is true", () => {
    renderLoginForm({ timedOut: true });
    expect(screen.getByText(/session timed out/i)).toBeInTheDocument();
  });

  it("calls loginByCode when the quick code form is submitted", async () => {
    const user = userEvent.setup();
    const loginByCode = vi.fn().mockResolvedValue(undefined);
    renderLoginForm({ loginByCode });

    await user.type(screen.getByPlaceholderText("ABC"), "XYZ");
    await user.click(screen.getByRole("button", { name: /sign in with code/i }));

    await waitFor(() => expect(loginByCode).toHaveBeenCalledWith("XYZ"));
  });

  it("keeps the quick code button disabled until 3 characters are entered", async () => {
    const user = userEvent.setup();
    renderLoginForm();

    const submitBtn = screen.getByRole("button", { name: /sign in with code/i });
    expect(submitBtn).toBeDisabled();

    await user.type(screen.getByPlaceholderText("ABC"), "AB");
    expect(submitBtn).toBeDisabled();

    await user.type(screen.getByPlaceholderText("ABC"), "C");
    expect(submitBtn).not.toBeDisabled();
  });
});
