"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import {
  createExpense,
  deleteExpense,
  downloadExpensesCsv,
  getBusiness,
  listExpenses,
  type BusinessDetail,
  type Expense,
  type ExpenseCategory,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

const CATEGORIES: ExpenseCategory[] = [
  "advertising",
  "cogs",
  "software",
  "contractors",
  "travel",
  "meals",
  "utilities",
  "supplies",
  "legal",
  "bank_fees",
  "shipping",
  "other",
];

export default function ExpensesPage({ params }: PageProps) {
  const { id } = use(params);
  const currentYear = new Date().getFullYear();

  const [biz, setBiz] = useState<BusinessDetail | null>(null);
  const [rows, setRows] = useState<Expense[]>([]);
  const [year, setYear] = useState<number>(currentYear);
  const [category, setCategory] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [showNew, setShowNew] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [b, r] = await Promise.all([
        getBusiness(id),
        listExpenses(id, {
          year,
          category: (category as ExpenseCategory) || undefined,
        }),
      ]);
      setBiz(b);
      setRows(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setHydrated(true);
    }
  }, [id, year, category]);

  useEffect(() => {
    void load();
  }, [load]);

  const totals = useMemo(() => {
    const byCategory: Record<string, number> = {};
    let total = 0;
    for (const r of rows) {
      byCategory[r.category] = (byCategory[r.category] ?? 0) + r.amount_cents;
      total += r.amount_cents;
    }
    return { byCategory, total };
  }, [rows]);

  const onExport = async () => {
    try {
      const blob = await downloadExpensesCsv(id, year);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${biz?.name ?? "business"}_expenses_${year}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onDelete = async (expenseId: string) => {
    if (!confirm("Delete this expense? This can't be undone.")) return;
    try {
      await deleteExpense(expenseId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-[1100px] px-6 py-8">
        <div className="mb-6 flex items-center gap-2 text-xs text-ink-3">
          <Link href="/businesses" className="hover:text-ink">
            Businesses
          </Link>
          <span aria-hidden>›</span>
          {biz ? (
            <Link href={`/businesses/${id}`} className="hover:text-ink">
              {biz.name}
            </Link>
          ) : (
            <span>—</span>
          )}
          <span aria-hidden>›</span>
          <span className="text-ink">Expenses</span>
        </div>

        <header className="mb-6 flex items-start justify-between gap-3">
          <div>
            <h1 className="font-serif text-[32px] leading-none text-ink">Expenses</h1>
            <p className="mt-2 text-[14px] text-ink-2">
              Every dollar, categorized. Export for tax prep or import from email.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setShowNew((v) => !v)}>
              {showNew ? "Close" : "+ New"}
            </Button>
            <Button variant="accent" onClick={onExport}>
              Export CSV ({year})
            </Button>
          </div>
        </header>

        {error && (
          <div className="mb-6 rounded-sm border border-terracotta/40 bg-terracotta/5 px-4 py-3 text-[13px] text-terracotta-2">
            {error}
          </div>
        )}

        {showNew && (
          <NewExpenseForm
            businessId={id}
            onCreated={() => {
              setShowNew(false);
              void load();
            }}
          />
        )}

        <div className="mb-6 flex flex-wrap items-end gap-3">
          <label className="space-y-1">
            <span className="text-[11px] uppercase tracking-[0.06em] text-ink-3">Year</span>
            <select
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="h-9 rounded-sm border border-rule bg-paper px-2 text-sm"
            >
              {[currentYear, currentYear - 1, currentYear - 2, currentYear - 3].map(
                (y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ),
              )}
            </select>
          </label>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] uppercase tracking-[0.06em] text-ink-3">
              Category
            </span>
            <div className="flex flex-wrap gap-1">
              <button
                type="button"
                onClick={() => setCategory("")}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[11px]",
                  !category
                    ? "bg-ink text-paper border-ink"
                    : "bg-paper text-ink-2 border-rule hover:bg-sand",
                )}
              >
                All
              </button>
              {CATEGORIES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCategory(c)}
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-[11px]",
                    category === c
                      ? "bg-ink text-paper border-ink"
                      : "bg-paper text-ink-2 border-rule hover:bg-sand",
                  )}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mb-6 flex items-baseline justify-between rounded-sm border border-rule bg-paper-2 p-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
              Total · {year}
            </div>
            <div className="font-serif text-[28px] text-ink tabular">
              ${(totals.total / 100).toFixed(2)}
            </div>
          </div>
          <div className="text-[11px] text-ink-3">
            {rows.length} expense{rows.length === 1 ? "" : "s"}
          </div>
        </div>

        {!hydrated ? (
          <div className="text-center text-[13px] text-ink-3">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="rounded-sm border border-rule bg-paper-2 p-6 text-center text-[13px] text-ink-3">
            No expenses yet. Add manual entries or connect Gmail to auto-sync.
          </div>
        ) : (
          <div className="rounded-sm border border-rule bg-paper overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-rule text-[11px] uppercase tracking-[0.06em] text-ink-3 text-left">
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Vendor</th>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2">Source</th>
                  <th className="px-3 py-2 text-right">Amount</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    className="border-b border-rule last:border-b-0 hover:bg-sand/30"
                  >
                    <td className="px-3 py-2 tabular">
                      {new Date(r.occurred_at).toLocaleDateString()}
                    </td>
                    <td className="px-3 py-2">{r.vendor}</td>
                    <td className="px-3 py-2">
                      <span className="rounded-full bg-sand px-1.5 py-0.5 text-[10px] uppercase tracking-wider">
                        {r.category}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-ink-3">{r.source}</td>
                    <td className="px-3 py-2 text-right tabular font-medium">
                      ${(r.amount_cents / 100).toFixed(2)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => void onDelete(r.id)}
                        className="text-[11px] text-ink-3 hover:text-terracotta"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}

function NewExpenseForm({
  businessId,
  onCreated,
}: {
  businessId: string;
  onCreated: () => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);
  const [vendor, setVendor] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState<ExpenseCategory>("software");
  const [description, setDescription] = useState("");
  const [receiptUrl, setReceiptUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    const cents = Math.round(Number(amount) * 100);
    if (!vendor.trim() || !amount || Number.isNaN(cents) || cents < 0) {
      setErr("Vendor + amount are required.");
      return;
    }
    setErr(null);
    setBusy(true);
    try {
      await createExpense(businessId, {
        occurred_at: new Date(date).toISOString(),
        amount_cents: cents,
        currency: "USD",
        vendor: vendor.trim(),
        category,
        description: description.trim() || undefined,
        receipt_url: receiptUrl.trim() || undefined,
      });
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-6 rounded-sm border border-rule bg-paper-2 p-4">
      <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3 mb-3">
        New expense
      </div>
      {err && (
        <p className="mb-3 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {err}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-5">
        <label className="space-y-1">
          <span className="text-[10px] uppercase tracking-[0.06em] text-ink-3">Date</span>
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} disabled={busy} />
        </label>
        <label className="space-y-1 sm:col-span-2">
          <span className="text-[10px] uppercase tracking-[0.06em] text-ink-3">Vendor</span>
          <Input value={vendor} onChange={(e) => setVendor(e.target.value)} placeholder="Stripe" disabled={busy} />
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase tracking-[0.06em] text-ink-3">
            Amount (USD)
          </span>
          <Input
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            disabled={busy}
          />
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase tracking-[0.06em] text-ink-3">Category</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as ExpenseCategory)}
            disabled={busy}
            className="flex h-10 w-full rounded-sm border border-rule bg-paper px-3 py-2 text-sm"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="text-[10px] uppercase tracking-[0.06em] text-ink-3">
            Description (optional)
          </span>
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What was this for?"
            disabled={busy}
          />
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase tracking-[0.06em] text-ink-3">
            Receipt URL (optional)
          </span>
          <Input
            type="url"
            value={receiptUrl}
            onChange={(e) => setReceiptUrl(e.target.value)}
            placeholder="https://…"
            disabled={busy}
          />
        </label>
      </div>
      <div className="mt-3 flex justify-end">
        <Button variant="accent" onClick={run} disabled={busy}>
          {busy ? "Saving…" : "Save expense"}
        </Button>
      </div>
    </section>
  );
}
