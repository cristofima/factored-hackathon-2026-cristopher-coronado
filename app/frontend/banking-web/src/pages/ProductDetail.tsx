import { useParams } from "react-router-dom";
import FinancialOverview from "@/components/FinancialOverview";

export default function ProductDetail() {
  const { productId } = useParams();
  return <FinancialOverview key={productId} productId={productId} />;
}
