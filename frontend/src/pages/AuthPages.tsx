import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheck } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { usePageTitle } from "../components/Layout";
import { Alert, Button, TextField } from "../components/ui";
import { DemoBanner } from "../components/DemoBanner";
import { useAuth } from "../lib/auth";

function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside aria-label="About AccessiScan AI" className="on-dark flex flex-col justify-between bg-navy-900 px-8 py-10 text-white lg:w-[44%] lg:px-14">
        <p className="text-xl font-semibold">
          AccessiScan <span className="text-accent-300">AI</span>
        </p>
        <div className="my-10 max-w-md">
          <p className="text-3xl font-semibold leading-tight">Find and fix accessibility barriers before your users hit them.</p>
          <ul className="mt-6 space-y-3 text-slate-200">
            {[
              "Real-browser scans with axe-core against WCAG 2.2 A/AA",
              "Clear severity, WCAG mapping and manual-review checklists",
              "Optional AI explanations and code-fix suggestions",
            ].map((t) => (
              <li key={t} className="flex gap-2">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-accent-300" aria-hidden="true" />
                {t}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-slate-300">Automated testing finds only part of WCAG issues. Results are not legal certification.</p>
      </aside>
      <main className="flex flex-1 flex-col items-center justify-center px-4 py-10">
        <div className="mb-6 w-full max-w-sm overflow-hidden rounded-lg empty:hidden"><DemoBanner /></div>
        <div className="w-full max-w-sm">
          <h1 className="text-2xl font-semibold text-navy-900">{title}</h1>
          {children}
        </div>
      </main>
    </div>
  );
}

const loginSchema = z.object({
  email: z.string().trim().min(1, "Enter your e-mail address").email("Enter a valid e-mail address"),
  password: z.string().min(1, "Enter your password"),
});

export function LoginPage() {
  usePageTitle("Sign in");
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const notice = (location.state as { message?: string } | null)?.message;
  const { register, handleSubmit, formState } = useForm<z.infer<typeof loginSchema>>({ resolver: zodResolver(loginSchema) });
  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      await login(v.email, v.password);
      navigate((location.state as { from?: string } | null)?.from ?? "/", { replace: true });
    } catch (e) {
      setError((e as Error).message);
    }
  });
  return (
    <AuthShell title="Sign in">
      <p className="mt-1 text-slate-700">
        New to AccessiScan?{" "}
        <Link to="/register" className="font-medium text-navy-800 underline">Create an account</Link>
      </p>
      <form className="mt-6 flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        {notice && <Alert tone="success" live>{notice}</Alert>}
        {error && <Alert tone="error" live>{error}</Alert>}
        <TextField label="E-mail address" type="email" autoComplete="email" required error={formState.errors.email?.message} {...register("email")} />
        <TextField label="Password" type="password" autoComplete="current-password" required error={formState.errors.password?.message} {...register("password")} />
        <Button type="submit" size="lg" loading={formState.isSubmitting}>Sign in</Button>
      </form>
    </AuthShell>
  );
}

const registerSchema = z
  .object({
    full_name: z.string().trim().max(200).optional(),
    email: z.string().trim().min(1, "Enter your e-mail address").email("Enter a valid e-mail address"),
    password: z
      .string()
      .min(10, "Use at least 10 characters")
      .max(128, "Use at most 128 characters")
      .refine((v) => /[a-z]/.test(v) && /[A-Z]/.test(v) && /\d/.test(v), "Include upper- and lower-case letters and a number"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "The passwords do not match" });

export function RegisterPage() {
  usePageTitle("Create account");
  const { register: signUp } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof registerSchema>>({ resolver: zodResolver(registerSchema) });
  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      await signUp(v.email, v.password, v.full_name ?? "");
      navigate("/", { replace: true });
    } catch (e) {
      setError((e as Error).message);
    }
  });
  return (
    <AuthShell title="Create your account">
      <p className="mt-1 text-slate-700">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-navy-800 underline">Sign in</Link>
      </p>
      <form className="mt-6 flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        {error && <Alert tone="error" live>{error}</Alert>}
        <TextField label="Full name" autoComplete="name" error={formState.errors.full_name?.message} {...register("full_name")} />
        <TextField label="E-mail address" type="email" autoComplete="email" required error={formState.errors.email?.message} {...register("email")} />
        <TextField label="Password" type="password" autoComplete="new-password" required hint="At least 10 characters with upper- and lower-case letters and a number." error={formState.errors.password?.message} {...register("password")} />
        <TextField label="Confirm password" type="password" autoComplete="new-password" required error={formState.errors.confirm?.message} {...register("confirm")} />
        <Button type="submit" size="lg" loading={formState.isSubmitting}>Create account</Button>
      </form>
    </AuthShell>
  );
}
