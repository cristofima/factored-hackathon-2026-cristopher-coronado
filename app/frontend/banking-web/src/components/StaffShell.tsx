import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/context/AuthContext";
import { Building2 } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/common/utils";

export default function StaffShell() {
  const { user, logout } = useAuth();
  const { t } = useTranslation();
  return <div className="min-h-screen bg-background">
    <header className="border-b bg-card shadow-sm">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <Building2 className="h-8 w-8 shrink-0 text-primary" aria-hidden="true" />
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-foreground">{t(user?.role === "admin" ? "Identity administration" : "Operator workspace")}</h1>
            <p className="break-words text-sm text-muted-foreground">{user?.name || user?.email}</p>
          </div>
        </div>
        <Button variant="outline" onClick={logout}>{t("Sign out")}</Button>
      </div>
    </header>
    {user?.role === "admin" && <nav aria-label={t("Identity administration")} className="mx-auto flex max-w-6xl flex-wrap gap-2 px-4 pt-6 sm:px-6">
      <NavLink to="/admin/operators" className={({ isActive }) => cn(buttonVariants({ variant: isActive ? "default" : "outline", size: "sm" }), !isActive && "bg-card")}>{t("Operators")}</NavLink>
      <NavLink to="/admin/customers" className={({ isActive }) => cn(buttonVariants({ variant: isActive ? "default" : "outline", size: "sm" }), !isActive && "bg-card")}>{t("Customer users")}</NavLink>
    </nav>}
    {user?.role === "operator" && <nav aria-label={t("Operator workspace")} className="mx-auto flex max-w-6xl gap-2 px-4 pt-6 sm:px-6">
      <NavLink to="/operator/support-cases" className={({ isActive }) => buttonVariants({ variant: isActive ? "default" : "outline", size: "sm" })}>{t("Review cases")}</NavLink>
    </nav>}
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6"><Outlet /></main>
  </div>;
}
