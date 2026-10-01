import { useState } from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  BarChart3,
  TrendingUp,
  ChevronLeft,
  ChevronRight,
  Wallet,
  PieChart,
  User,
  HelpCircle,
  ShieldAlert,
} from "lucide-react";

const navigation = [
  { name: "Dashboard", href: "/", icon: BarChart3 },
  { name: "Credit Cards", href: "/credit-cards", icon: Wallet },
  { name: "Investment Portfolio", href: "/portfolio", icon: PieChart },
  { name: "Transaction Analytics", href: "/analytics", icon: TrendingUp },
  { name: "Account", href: "/account", icon: User },
  { name: "Transaction Disputes", href: "/support-cases", icon: ShieldAlert },
  { name: "Support", href: "/support", icon: HelpCircle },
];

export default function Sidebar() {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div
      className={`bg-sidebar border-r border-sidebar-border transition-all duration-300 shadow-professional ${
        collapsed ? "w-16" : "w-64"
      }`}
    >
      <nav className="mt-3 px-3">
        <div className="mb-2 flex justify-end">
          <button
            onClick={() => setCollapsed(!collapsed)}
            aria-label={t(
              collapsed ? "Expand navigation" : "Collapse navigation",
            )}
            title={t(collapsed ? "Expand navigation" : "Collapse navigation")}
            className="p-1 rounded hover:bg-slate-100 transition-colors"
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4 text-slate-600" />
            ) : (
              <ChevronLeft className="h-4 w-4 text-slate-600" />
            )}
          </button>
        </div>
        <ul className="space-y-1">
          {navigation.map((item) => (
            <li key={item.name}>
              <NavLink
                to={item.href}
                aria-label={t(item.name)}
                title={collapsed ? t(item.name) : undefined}
                className={({ isActive }) =>
                  `flex items-center px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
                  }`
                }
              >
                <item.icon className={`h-5 w-5 ${collapsed ? "" : "mr-3"}`} />
                {!collapsed && <span>{t(item.name)}</span>}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
