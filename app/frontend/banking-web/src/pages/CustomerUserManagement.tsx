import { type FormEvent, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, errorTranslationKey } from "@/api/errors";
import { changeCustomerUser, listCustomerUsers, type CustomerUser, type CustomerUserAction } from "@/api/customerUserClient";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogCancel } from "@/components/ui/alert-dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Selection = { customer: CustomerUser; action: CustomerUserAction };

export default function CustomerUserManagement() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const locale = user?.locale ?? "en";
  const dateFormatter = new Intl.DateTimeFormat(["en", "es", "pt"].includes(locale) ? locale : "en", { dateStyle: "medium", timeStyle: "short" });
  const queryClient = useQueryClient();
  const customers = useQuery({ queryKey: ["admin", "customers"], queryFn: ({ signal }) => listCustomerUsers(signal), retry: false });
  const [selection, setSelection] = useState<Selection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const pending = useRef<AbortController | null>(null);

  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    if (customers.error instanceof ApiError && customers.error.code === "AUTH_REQUIRED") logout();
  }, [customers.error, logout]);

  const close = () => { setSelection(null); setError(null); };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selection || busy) return;
    setError(null);
    setSuccess(false);
    const controller = new AbortController();
    pending.current?.abort();
    pending.current = controller;
    setBusy(true);
    try {
      await changeCustomerUser(selection.customer.sub, selection.action, controller.signal);
      controller.signal.throwIfAborted();
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
      controller.signal.throwIfAborted();
      setSelection(null);
      setSuccess(true);
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (failure instanceof ApiError && failure.code === "AUTH_REQUIRED") logout();
      else setError(errorTranslationKey(failure, "Customer operation unavailable"));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  return <section className="space-y-6">
    <div className="space-y-2">
      <h2 className="text-2xl font-bold text-foreground">{t("Customer users")}</h2>
      <p className="max-w-3xl text-sm text-muted-foreground">{t("Manage existing customer sign-in access only. Banking customer status and financial data are unchanged.")}</p>
    </div>
    {success && <Alert role="status"><AlertDescription>{t("Customer user updated")}</AlertDescription></Alert>}
    {error && !selection && <Alert variant="destructive"><AlertDescription>{t(error)}</AlertDescription></Alert>}
    <Card>
      <CardContent className="p-0">
        {customers.isPending ? <p role="status" className="p-6 text-sm text-muted-foreground">{t("Loading customer users...")}</p> : customers.isError ?
          <Alert variant="destructive"><AlertDescription className="space-y-3"><p>{t(errorTranslationKey(customers.error, "Customer list unavailable"))}</p><Button variant="outline" onClick={() => void customers.refetch()}>{t("Retry")}</Button></AlertDescription></Alert> :
          customers.data.length === 0 ? <p className="p-6 text-sm text-muted-foreground">{t("No customer users")}</p> : <Table>
            <TableHeader><TableRow>{["Email", "Name", "Customer ID", "Locale", "Status", "Last updated", "Actions"].map((label) => <TableHead key={label} className="whitespace-nowrap">{t(label)}</TableHead>)}</TableRow></TableHeader>
            <TableBody>{customers.data.map((customer) => {
              const action = customer.status === "active" ? "deactivate" : "activate";
              const label = action === "activate" ? "Activate" : "Deactivate";
              return <TableRow key={customer.sub}>
                <TableCell className="font-medium">{customer.email}</TableCell><TableCell>{customer.name || "—"}</TableCell><TableCell className="text-muted-foreground">{customer.customer_id}</TableCell>
                <TableCell>{t({ en: "English", es: "Spanish", pt: "Portuguese" }[customer.locale])}</TableCell>
                <TableCell><Badge variant={customer.status === "active" ? "default" : "secondary"}>{t(customer.status === "active" ? "Active" : "Inactive")}</Badge></TableCell>
                <TableCell className="whitespace-nowrap text-muted-foreground"><time dateTime={customer.updated_at} title={customer.updated_at}>{dateFormatter.format(new Date(customer.updated_at))}</time></TableCell>
                <TableCell><Button size="sm" variant="outline" disabled={!!selection || busy} aria-label={`${t(label)} ${customer.email}`} onClick={() => { setError(null); setSuccess(false); setSelection({ customer, action }); }}>{t(label)}</Button></TableCell>
              </TableRow>;
            })}</TableBody>
          </Table>}
      </CardContent>
    </Card>
    {selection && <AlertDialog open onOpenChange={(open) => { if (!open && !busy) close(); }}>
      <AlertDialogContent className="max-h-[90dvh] w-[calc(100%-2rem)] overflow-y-auto" onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("Confirm customer operation")}</AlertDialogTitle>
          <AlertDialogDescription>{t("Changing sign-in access revokes existing sessions. The customer must sign in again after activation.")}</AlertDialogDescription>
        </AlertDialogHeader>
        {error && <Alert variant="destructive"><AlertDescription>{t(error)}</AlertDescription></Alert>}
        <form onSubmit={submit} className="space-y-4" aria-label={t("Confirm customer operation")}>
          <p className="text-sm font-medium break-words">{t(selection.action === "activate" ? "Activate" : "Deactivate")}: {selection.customer.email}</p>
          <fieldset disabled={busy} className="flex flex-wrap gap-2"><Button type="submit" variant={selection.action === "deactivate" ? "destructive" : "default"}>{t(busy ? "Saving..." : "Confirm")}</Button><AlertDialogCancel asChild><Button type="button" variant="outline" disabled={busy} onClick={close}>{t("Cancel")}</Button></AlertDialogCancel></fieldset>
        </form>
      </AlertDialogContent>
    </AlertDialog>}
  </section>;
}
