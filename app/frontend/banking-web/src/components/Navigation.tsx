import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronDown, Settings, LogOut, User, Building2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useTranslation } from "react-i18next";

export default function Navigation() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const displayName = user?.name || user?.email || t("Account");
  const nameParts = user?.name?.trim().split(/\s+/);
  const lastInitial =
    nameParts && nameParts.length > 1 ? nameParts[nameParts.length - 1][0] : "";
  const initials = nameParts?.length
    ? `${nameParts[0][0]}${lastInitial}`.toUpperCase()
    : user?.email?.slice(0, 2).toUpperCase() || "EB";

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  const handleSettings = () => {
    navigate("/account");
  };

  return (
    <nav className="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between shadow-sm">
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-3">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center shadow-md">
            <Building2 className="h-5 w-5 text-white" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900 leading-tight">
              {t("Home Banking Assistant")}
            </h2>
            <p className="text-xs text-slate-500 leading-none">
              {t("Demo Application")}
            </p>
          </div>
        </div>
      </div>

      <div className="flex items-center space-x-4">
        <div className="text-right min-w-0 max-w-48 sm:max-w-64">
          <div
            className="text-sm font-medium text-slate-900 truncate"
            title={displayName}
          >
            {displayName}
          </div>
          <div className="text-xs text-slate-500 truncate">
            {user?.email ?? t("Loading...")}
          </div>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              className="flex items-center space-x-2 h-auto p-2 hover:bg-slate-50"
            >
              <Avatar className="h-8 w-8">
                <AvatarImage alt={displayName} />
                <AvatarFallback className="bg-primary text-primary-foreground text-sm">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <ChevronDown className="h-4 w-4 text-slate-500" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 bg-white">
            <DropdownMenuLabel>
              <div>
                <div className="font-medium break-words">{displayName}</div>
                <div className="text-xs text-slate-400">
                  {t("Customer {{id}}", { id: user?.customerId })}
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={handleSettings}
              className="cursor-pointer"
            >
              <User className="mr-2 h-4 w-4" />
              {t("Profile")}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={handleSettings}
              className="cursor-pointer"
            >
              <Settings className="mr-2 h-4 w-4" />
              {t("Account Settings")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={handleLogout}
              className="cursor-pointer text-red-600 hover:text-red-600 hover:bg-red-50"
            >
              <LogOut className="mr-2 h-4 w-4" />
              {t("Sign Out")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </nav>
  );
}
