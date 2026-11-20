// Shapes returned by the SmartSpend API. Money is always a decimal string like "450.00".
export type Money = string;
export type TxnType = "income" | "expense";
export type BudgetStatus = "healthy" | "approaching" | "near_limit" | "exceeded" | "no_budget";

export interface User {
  id: number;
  name: string;
  email: string;
  currency: string;
  timezone: string;
  monthly_income: Money | null;
  onboarded: boolean;
  created_at: string;
}

export interface Category {
  id: number;
  name: string;
  type: TxnType;
  is_default: boolean;
}

export interface Transaction {
  id: number;
  amount: Money;
  currency: string;
  type: TxnType;
  category: Category;
  description: string;
  transaction_date: string;
  payment_method: string | null;
  notes: string | null;
  source: "manual" | "ai" | "import";
  is_future: boolean;
  created_at: string;
  updated_at: string;
}

export interface TransactionPage {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface Budget {
  id: number;
  category: Category | null;
  amount: Money;
  spent: Money;
  remaining: Money;
  utilisation: string | null;
  status: BudgetStatus;
  year: number;
  month: number;
}

export interface BudgetSummary {
  year: number;
  month: number;
  currency: string;
  total: Budget | null;
  categories: Budget[];
  total_expenses: Money;
  unbudgeted_expenses: Money;
}

export interface Overview {
  year: number;
  month: number;
  label: string;
  currency: string;
  is_current_month: boolean;
  days_elapsed: number;
  days_in_month: number;
  income: Money;
  expenses: Money;
  net: Money;
  budget: Money | null;
  budget_remaining: Money | null;
  budget_utilisation: string | null;
  comparison: { label: string; expenses: Money; change: Money; change_percent: string | null; note: string };
  transaction_count: number;
  recent: Transaction[];
  unread_notifications: number;
  has_any_transactions: boolean;
}

export interface MonthlyPoint {
  year: number;
  month: number;
  label: string;
  income: Money;
  expenses: Money;
  net: Money;
}

export interface CategoryBreakdown {
  total: Money;
  items: { category_id: number; name: string; total: Money; count: number; share: string | null; previous_total: Money }[];
}

export interface DailyPoint {
  date: string;
  day: number;
  expenses: Money;
  cumulative: Money;
}

export interface Goal {
  id: number;
  title: string;
  target_amount: Money;
  current_amount: Money;
  target_date: string | null;
  status: "active" | "completed" | "archived";
  progress: string;
  remaining: Money;
  monthly_needed: Money | null;
  created_at: string;
}

export interface Notification {
  id: number;
  type: string;
  title: string;
  message: string;
  meta: Record<string, unknown>;
  is_read: boolean;
  created_at: string;
}

export interface Draft {
  amount: Money | null;
  currency: string;
  transaction_type: TxnType | "unknown";
  category: string | null;
  category_id: number | null;
  description: string;
  transaction_date: string | null;
  payment_method: string | null;
}

export interface ParseResult {
  draft: Draft;
  confidence: number;
  requires_confirmation: true;
  missing_fields: string[];
  needs_clarification: boolean;
  clarification_question: string | null;
  provider: string;
}

export interface Fact {
  label: string;
  value: string;
}

export interface ChatReply {
  conversation_id: number;
  message_id: number;
  answer: string;
  intent: string;
  period: { start: string; end: string; label: string } | null;
  facts: { period: string | null; items: Fact[]; notes: string[] };
  kind: "answer" | "clarification" | "boundary" | "draft" | "education";
  draft: ParseResult | null;
  links: { label: string; to: string }[];
  provider: string;
  grounded: boolean;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface StoredMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  meta: Partial<ChatReply>;
  created_at: string;
}

export interface Insight {
  id: string;
  title: string;
  summary: string;
  evidence: Record<string, string | number>;
  suggested_action: string;
  estimated_impact: string | null;
  limitations: string[];
  kind: string;
  generated_at: string;
}

export interface AIStatus {
  provider: string;
  live: boolean;
  model: string | null;
  disclaimer: string;
}
