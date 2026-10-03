import { type FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, errorTranslationKey } from "@/api/errors";
import { changeOperator, createOperator, createOperatorSchema, listOperators, resetPasswordSchema, type Operator, type OperatorAction } from "@/api/operatorClient";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogCancel } from "@/components/ui/alert-dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Selection = { operator: Operator; action: OperatorAction };

export function OperatorCreate() {
  return <OperatorManagement create />;
}

export default function OperatorManagement({ create: creating = false }: { create?: boolean } = {}) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const localeClaim = user?.locale ?? "en";
  const dateLocale = ["en", "es", "pt"].includes(localeClaim) ? localeClaim : "en";
  const dateFormatter = new Intl.DateTimeFormat(dateLocale, { dateStyle: "medium", timeStyle: "short" });
  const queryClient = useQueryClient();
  const operators = useQuery({ queryKey: ["admin", "operators"], queryFn: ({ signal }) => listOperators(signal), retry: false, enabled: !creating });
  const [selection, setSelection] = useState<Selection | null>(null);
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [locale, setLocale] = useState<"en" | "es" | "pt">("en");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const pending = useRef<AbortController | null>(null);

  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    if (!creating && operators.error instanceof ApiError && operators.error.code === "AUTH_REQUIRED") logout();
  }, [creating, operators.error, logout]);

  const close = () => {
    pending.current?.abort();
    setBusy(false);
    setPassword("");
    setEmail("");
    setFirstName("");
    setLastName("");
    setLocale("en");
    setSelection(null);
    setError(null);
    if (creating) navigate("/admin/operators");
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || (!creating && !selection)) return;
    setError(null);
    setSuccess(false);
    const input = createOperatorSchema.safeParse({ email, password, locale, first_name: firstName, last_name: lastName });
    if ((creating && !input.success) || (selection?.action === "reset-password" && !resetPasswordSchema.safeParse({ password }).success)) {
      setPassword("");
      setError("Check the operator details. Passwords must contain 12 to 256 characters.");
      return;
    }
    const controller = new AbortController();
    pending.current?.abort();
    pending.current = controller;
    setBusy(true);
    const secret = password;
    setPassword("");
    try {
      if (creating && input.success) await createOperator(input.data, controller.signal);
      else if (selection) await changeOperator(selection.operator.sub, selection.action, controller.signal, selection.action === "reset-password" ? secret : undefined);
      else return;
      controller.signal.throwIfAborted();
      setPassword("");
      setEmail("");
      setFirstName("");
      setLastName("");
      setLocale("en");
      await queryClient.invalidateQueries({ queryKey: ["admin", "operators"] });
      controller.signal.throwIfAborted();
      setSelection(null);
      setSuccess(true);
      if (creating) navigate("/admin/operators");
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (failure instanceof ApiError && failure.code === "AUTH_REQUIRED") logout();
      else setError(errorTranslationKey(failure, "Operator operation unavailable"));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  const operationForm = <form noValidate onSubmit={submit} className="space-y-4" aria-label={t(creating ? "Create operator" : "Confirm operator operation")}>
    <fieldset disabled={busy} className="space-y-4">
      {creating && <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2 sm:col-span-2"><Label htmlFor="operator-email">{t("Email")}</Label><Input id="operator-email" type="email" maxLength={120} required value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="off" /></div>
        <div className="space-y-2"><Label htmlFor="operator-first-name">{t("First name")}</Label><Input id="operator-first-name" maxLength={50} required value={firstName} onChange={(event) => setFirstName(event.target.value)} autoComplete="off" /></div>
        <div className="space-y-2"><Label htmlFor="operator-last-name">{t("Last name")}</Label><Input id="operator-last-name" maxLength={50} required value={lastName} onChange={(event) => setLastName(event.target.value)} autoComplete="off" /></div>
        <div className="space-y-2"><Label htmlFor="operator-locale">{t("Locale")}</Label><Select value={locale} disabled={busy} onValueChange={(value) => setLocale(value as typeof locale)}><SelectTrigger id="operator-locale"><SelectValue /></SelectTrigger><SelectContent>{(["en", "es", "pt"] as const).map((value) => <SelectItem key={value} value={value}>{t({ en: "English", es: "Spanish", pt: "Portuguese" }[value])}</SelectItem>)}</SelectContent></Select></div>
      </div>}
      {(creating || selection?.action === "reset-password") && <div className="space-y-2"><Label htmlFor="operator-password">{t("New password")}</Label><Input id="operator-password" type="password" autoComplete="new-password" minLength={12} maxLength={256} required value={password} onChange={(event) => setPassword(event.target.value)} aria-describedby="operator-password-help" /><p id="operator-password-help" className="text-sm text-muted-foreground">{t("Passwords must contain 12 to 256 characters.")}</p></div>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant={selection?.action === "deactivate" ? "destructive" : "default"}>{t(busy ? "Saving..." : "Confirm")}</Button>
        {creating ? <Button type="button" variant="outline" disabled={busy} onClick={close}>{t("Cancel")}</Button> : <AlertDialogCancel asChild><Button type="button" variant="outline" disabled={busy} onClick={close}>{t("Cancel")}</Button></AlertDialogCancel>}
      </div>
    </fieldset>
  </form>;

  return <section className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-foreground">{t(creating ? "Create operator" : "Operators")}</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">{t("This workspace manages operator identities only. Financial data and reviewer decisions are unavailable.")}</p>
      </div>
      {!creating && <Button disabled={!!selection || busy} onClick={() => navigate("/admin/operators/create")}>{t("Create operator")}</Button>}
    </div>
    {success && <Alert role="status"><AlertDescription>{t("Operator updated")}</AlertDescription></Alert>}
    {error && !selection && <Alert variant="destructive"><AlertDescription>{t(error)}</AlertDescription></Alert>}
    {!creating && <Card>
      <CardContent className="p-0">
        {operators.isPending ? <p role="status" className="p-6 text-sm text-muted-foreground">{t("Loading operators...")}</p> : operators.isError ?
          <Alert variant="destructive"><AlertDescription className="space-y-3"><p>{t(errorTranslationKey(operators.error, "Operator list unavailable"))}</p><Button variant="outline" onClick={() => void operators.refetch()}>{t("Retry")}</Button></AlertDescription></Alert> :
          operators.data.length === 0 ? <p className="p-6 text-sm text-muted-foreground">{t("No operators")}</p> : <Table>
            <TableHeader><TableRow>{["Email", "Name", "Locale", "Status", "Last updated", "Actions"].map((label) => <TableHead key={label} className="whitespace-nowrap">{t(label)}</TableHead>)}</TableRow></TableHeader>
            <TableBody>{operators.data.map((operator) => <TableRow key={operator.sub}>
              <TableCell className="font-medium">{operator.email}</TableCell><TableCell>{operator.name || "—"}</TableCell>
              <TableCell>{t({ en: "English", es: "Spanish", pt: "Portuguese" }[operator.locale])}</TableCell>
              <TableCell><Badge variant={operator.status === "active" ? "default" : "secondary"}>{t(operator.status === "active" ? "Active" : "Inactive")}</Badge></TableCell>
              <TableCell className="whitespace-nowrap text-muted-foreground"><time dateTime={operator.updated_at} title={operator.updated_at}>{dateFormatter.format(new Date(operator.updated_at))}</time></TableCell>
              <TableCell><div className="flex flex-wrap gap-2">{([operator.status === "active" ? "deactivate" : "activate", "reset-password"] as OperatorAction[]).map((action) => <Button key={action} size="sm" variant="outline" disabled={creating || !!selection || busy} aria-label={`${t(action === "activate" ? "Activate" : action === "deactivate" ? "Deactivate" : "Reset password")} ${operator.email}`} onClick={() => { close(); setSuccess(false); setSelection({ operator, action }); }}>{t(action === "activate" ? "Activate" : action === "deactivate" ? "Deactivate" : "Reset password")}</Button>)}</div></TableCell>
            </TableRow>)}</TableBody>
          </Table>}
      </CardContent>
    </Card>}
    {creating && <Card>
      <CardHeader><CardTitle className="text-lg">{t("Create operator")}</CardTitle></CardHeader>
      <CardContent>{operationForm}</CardContent>
    </Card>}
    {!creating && selection && <AlertDialog open onOpenChange={(open) => { if (!open && !busy) close(); }}>
      <AlertDialogContent className="max-h-[90dvh] w-[calc(100%-2rem)] overflow-y-auto" onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("Confirm operator operation")}</AlertDialogTitle>
          <AlertDialogDescription>{t(selection.action === "activate" ? "Activate" : selection.action === "deactivate" ? "Deactivate" : "Reset password")}: {selection.operator.email}</AlertDialogDescription>
        </AlertDialogHeader>
        {error && <Alert variant="destructive"><AlertDescription>{t(error)}</AlertDescription></Alert>}
        {operationForm}
      </AlertDialogContent>
    </AlertDialog>}
  </section>;
}
