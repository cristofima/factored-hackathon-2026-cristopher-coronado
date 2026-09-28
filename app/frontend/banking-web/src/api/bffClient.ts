// BFFClient for real REST API calls
import { CreditCard } from "@/models/CreditCard";
import { CreditCardTransaction } from "@/models/CreditCardTransaction";
import { Payment } from "@/models/Payments";
import { UserProfile } from "@/models/UserProfile";

const LOCAL_API_URL = import.meta.env.VITE_BACKEND_URI || "/api";
const ACCOUNT_API_URL = import.meta.env.VITE_ACCOUNT_API_URL || LOCAL_API_URL;
const TRANSACTION_API_URL = import.meta.env.VITE_TRANSACTION_API_URL || LOCAL_API_URL;

export class BFFClient {
  async getUserProfile(): Promise<UserProfile> {
    throw new Error(
      "User profiles are unavailable until PostgreSQL-backed authentication is enabled.",
    );
  }

  async getPayments(): Promise<Payment[]> {
    const transactionAPIUrl = `${TRANSACTION_API_URL}/transactions`;

    const accountId = (await this.getUserProfile()).accountId;
    const response = await fetch(`${transactionAPIUrl}/${accountId}?transaction_type=payment`);
    if (!response.ok) {
      throw new Error("Failed to fetch payments");
    }
    const data = await response.json();
    // Optionally map to Payment instances if needed
    return data;
  }

  async getCards(): Promise<CreditCard[]> {
    const accountsAPIUrl = `${ACCOUNT_API_URL}/accounts`;

    const accountId = (await this.getUserProfile()).accountId;
    const response = await fetch(`${accountsAPIUrl}/${accountId}/cards`);
    if (!response.ok) {
      throw new Error("Failed to fetch payments");
    }
    const data = await response.json();
    // Optionally map to Payment instances if needed
    return data;
  }

  async getCardTransactions(cardId: string | null): Promise<CreditCardTransaction[]> {
    const transactionAPIUrl = `${TRANSACTION_API_URL}/transactions`;

    const accountId = (await this.getUserProfile()).accountId;
    const cardIdParam = cardId ? `&card_id=${cardId}` : "";
    const response = await fetch(`${transactionAPIUrl}/${accountId}?transaction_type=payment&payment_type=CreditCard${cardIdParam}`);
    if (!response.ok) {
      throw new Error("Failed to fetch payments");
    }
    const data = await response.json();
    // Optionally map to Payment instances if needed
    return data;
  }


}

export const bffClient = new BFFClient();
