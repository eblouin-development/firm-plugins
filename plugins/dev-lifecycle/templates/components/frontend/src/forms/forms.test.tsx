import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { z } from "zod";
import type { ErrorEnvelope } from "@repo/api-client";
import { ApiError } from "../errors/ApiError";
import { applyEnvelopeToForm } from "./applyEnvelopeToForm";
import { useZodForm } from "./useZodForm";
import { FieldError } from "./FieldError";

describe("applyEnvelopeToForm", () => {
  it("maps a 422 validation_failed envelope onto per-field and root errors", async () => {
    const { result } = renderHook(() => useForm<{ email: string; password: string }>());

    const apiError = new ApiError(422, {
      error: {
        code: "validation_failed",
        message: "Validation failed",
        details: [
          { field: "email", message: "Email is already taken" },
          { message: "Passwords must differ from your email" }, // no field → root
        ],
      },
    } as ErrorEnvelope);

    let applied = false;
    act(() => {
      applied = applyEnvelopeToForm(apiError, result.current.setError);
    });
    expect(applied).toBe(true);

    await waitFor(() =>
      expect(result.current.formState.errors.email?.message).toBe("Email is already taken"),
    );
    const rootError = (result.current.formState.errors as Record<string, { message?: string }>)
      .root;
    expect(rootError?.message).toBe("Passwords must differ from your email");
  });

  it("accepts a raw ErrorEnvelope (not only an ApiError)", async () => {
    const { result } = renderHook(() => useForm<{ email: string }>());
    const raw: ErrorEnvelope = {
      error: {
        code: "validation_failed",
        message: "bad",
        details: [{ field: "email", message: "required" }],
      },
    } as ErrorEnvelope;

    act(() => {
      applyEnvelopeToForm(raw, result.current.setError);
    });
    await waitFor(() => expect(result.current.formState.errors.email?.message).toBe("required"));
  });

  it("returns false and sets nothing for a non-validation error", () => {
    const { result } = renderHook(() => useForm<{ email: string }>());
    const apiError = new ApiError(409, {
      error: { code: "conflict", message: "already exists" },
    } as ErrorEnvelope);

    let applied = true;
    act(() => {
      applied = applyEnvelopeToForm(apiError, result.current.setError);
    });
    expect(applied).toBe(false);
    expect(result.current.formState.errors.email).toBeUndefined();
  });
});

describe("useZodForm + FieldError", () => {
  const schema = z.object({ email: z.string().min(1, "Email is required") });

  const TestForm = ({ onValid }: { onValid: (values: { email: string }) => void }) => {
    const { register, handleSubmit, formState } = useZodForm(schema);
    return (
      <form onSubmit={handleSubmit(onValid)}>
        <input aria-label="email" {...register("email")} />
        <FieldError error={formState.errors.email} />
        <button type="submit">submit</button>
      </form>
    );
  };

  it("surfaces the zod validation message through FieldError on submit", async () => {
    const user = userEvent.setup();
    const onValid = vi.fn();
    render(<TestForm onValid={onValid} />);

    await user.click(screen.getByRole("button", { name: "submit" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email is required");
    expect(onValid).not.toHaveBeenCalled();
  });

  it("submits valid values and clears the error", async () => {
    const user = userEvent.setup();
    const onValid = vi.fn();
    render(<TestForm onValid={onValid} />);

    await user.type(screen.getByLabelText("email"), "a@b.com");
    await user.click(screen.getByRole("button", { name: "submit" }));

    await waitFor(() => expect(onValid).toHaveBeenCalledTimes(1));
    expect(onValid.mock.calls[0]?.[0]).toEqual({ email: "a@b.com" });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("FieldError", () => {
  it("renders a string message with role=alert", () => {
    render(<FieldError error="something is wrong" />);
    expect(screen.getByRole("alert")).toHaveTextContent("something is wrong");
  });

  it("reads .message from an RHF field-error object", () => {
    render(<FieldError error={{ type: "server", message: "from RHF" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("from RHF");
  });

  it("renders nothing when there is no message", () => {
    const { container } = render(<FieldError />);
    expect(container).toBeEmptyDOMElement();
  });
});
