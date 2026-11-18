import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { api, del, patch, post } from "../api/client";
import type { AIStatus, User } from "../api/types";
import { usePageTitle } from "../components/Layout";
import { Alert, Button, Card, Checkbox, Dialog, PageHeader, TextField } from "../components/ui";
import { useAuth } from "../lib/auth";
import { formatDate } from "../lib/format";

const pwSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password"),
    new_password: z
      .string()
      .min(10, "Use at least 10 characters")
      .refine((v) => /[a-z]/.test(v) && /[A-Z]/.test(v) && /\d/.test(v), "Include upper- and lower-case letters and a number"),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "The passwords do not match" });

export default function SettingsPage() {
  usePageTitle("Settings");
  const { user, logout, endSession } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState(user?.full_name ?? "");
  const [notifyComplete, setNotifyComplete] = useState(user?.notify_scan_complete ?? true);
  const [notifyRegression, setNotifyRegression] = useState(user?.notify_regressions ?? true);
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePw, setDeletePw] = useState("");
  const ai = useQuery({ queryKey: ["ai-status"], queryFn: () => api<AIStatus>("/ai/status") });

  const saveProfile = useMutation({
    mutationFn: () => patch<User>("/users/me", { full_name: name, notify_scan_complete: notifyComplete, notify_regressions: notifyRegression }),
    onSuccess: (u) => {
      qc.setQueryData(["me"], u);
      setProfileMsg("Profile saved.");
    },
  });
  const pwForm = useForm<z.infer<typeof pwSchema>>({ resolver: zodResolver(pwSchema) });
  const changePw = pwForm.handleSubmit(async (v) => {
    try {
      await post("/users/me/password", { current_password: v.current_password, new_password: v.new_password });
      pwForm.reset();
      endSession();
      navigate("/login", { state: { message: "Password changed. All sessions were signed out – sign in with your new password." } });
    } catch (e) {
      pwForm.setError("current_password", { message: (e as Error).message });
    }
  });
  const logoutAll = useMutation({ mutationFn: () => post("/auth/logout-all"), onSuccess: () => logout() });
  const deleteAccount = useMutation({
    mutationFn: () => del("/users/me", { password: deletePw }),
    onSuccess: () => {
      endSession();
      navigate("/register");
    },
  });

  return (
    <>
      <PageHeader title="Settings" description="Manage your profile, notifications, password and account." />
      <div className="grid gap-6 xl:grid-cols-2">
        <Card aria-labelledby="profile-h">
          <h2 id="profile-h" className="mb-4 font-semibold text-navy-900">Profile and notifications</h2>
          <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); setProfileMsg(null); saveProfile.mutate(); }}>
            <TextField label="E-mail address" value={user?.email ?? ""} readOnly hint="The e-mail address cannot be changed." />
            <TextField label="Full name" autoComplete="name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium text-slate-900">In-app notifications</legend>
              <Checkbox label="When my scans complete or fail" checked={notifyComplete} onChange={(e) => setNotifyComplete(e.target.checked)} />
              <Checkbox label="When a re-scan finds new violations or regressions" checked={notifyRegression} onChange={(e) => setNotifyRegression(e.target.checked)} />
            </fieldset>
            <div><Button type="submit" loading={saveProfile.isPending}>Save profile</Button></div>
            {profileMsg && <Alert tone="success" live>{profileMsg}</Alert>}
            {saveProfile.error && <Alert tone="error" live>{(saveProfile.error as Error).message}</Alert>}
            <p className="text-xs text-slate-700">Member since {formatDate(user?.created_at, false)}</p>
          </form>
        </Card>

        <Card aria-labelledby="pw-h">
          <h2 id="pw-h" className="mb-4 font-semibold text-navy-900">Change password</h2>
          <form className="flex flex-col gap-4" onSubmit={changePw} noValidate>
            <TextField label="Current password" type="password" autoComplete="current-password" required error={pwForm.formState.errors.current_password?.message} {...pwForm.register("current_password")} />
            <TextField label="New password" type="password" autoComplete="new-password" required hint="At least 10 characters with upper- and lower-case letters and a number." error={pwForm.formState.errors.new_password?.message} {...pwForm.register("new_password")} />
            <TextField label="Confirm new password" type="password" autoComplete="new-password" required error={pwForm.formState.errors.confirm?.message} {...pwForm.register("confirm")} />
            <div><Button type="submit" loading={pwForm.formState.isSubmitting}>Change password</Button></div>
          </form>
        </Card>

        <Card aria-labelledby="ai-h">
          <h2 id="ai-h" className="mb-2 font-semibold text-navy-900">AI provider</h2>
          {ai.data?.enabled ? (
            <p className="text-sm text-slate-800">AI features are enabled using <strong>{ai.data.provider}</strong> ({ai.data.model}). {ai.data.used_today} of {ai.data.daily_limit} requests used in the last 24 hours.</p>
          ) : (
            <Alert tone="info">{ai.data?.message ?? "AI is not configured."}</Alert>
          )}
          <p className="mt-2 text-xs text-slate-700">API keys are configured by the server administrator in environment variables and are never sent to the browser.</p>
        </Card>

        <Card aria-labelledby="security-h">
          <h2 id="security-h" className="mb-2 font-semibold text-navy-900">Sessions and account</h2>
          <div className="flex flex-col items-start gap-3">
            <Button variant="secondary" loading={logoutAll.isPending} onClick={() => logoutAll.mutate()}>Sign out of all devices</Button>
            <Button variant="danger" onClick={() => setDeleteOpen(true)}>Delete account</Button>
          </div>
        </Card>
      </div>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen} title="Delete your account?" description="This permanently deletes your account, websites, scans, issues, notes and reports. This cannot be undone.">
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); deleteAccount.mutate(); }}>
          <TextField label="Confirm with your password" type="password" autoComplete="current-password" required value={deletePw} onChange={(e) => setDeletePw(e.target.value)} error={deleteAccount.error ? (deleteAccount.error as Error).message : undefined} />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDeleteOpen(false)}>Cancel</Button>
            <Button type="submit" variant="danger" loading={deleteAccount.isPending} disabled={!deletePw}>Delete account permanently</Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
