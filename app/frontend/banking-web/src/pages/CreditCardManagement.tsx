import { CreditCard } from "lucide-react";

const CreditCardManagement = () => (
  <section className="p-6 space-y-6">
    <h1 className="text-2xl font-bold">Credit Cards</h1>
    <div role="status" className="flex items-start gap-3 border-t py-6">
      <CreditCard
        className="h-6 w-6 shrink-0 text-muted-foreground"
        aria-hidden="true"
      />
      <div className="space-y-1">
        <h2 className="text-base font-medium">Credit cards are unavailable</h2>
        <p className="text-sm text-muted-foreground">
          Card management is not available in this prototype.
        </p>
      </div>
    </div>
  </section>
);

export default CreditCardManagement;
