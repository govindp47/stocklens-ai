// Placeholder page — replaced in full by T-043 (Playground implementation)
export default function HomePage() {
  return (
    <div className="flex min-h-[calc(100vh-3rem)] flex-col items-center justify-center gap-6 px-4">
      <h1 className="text-2xl font-semibold text-neutral-800">StockLens AI</h1>
      <p className="text-neutral-500">Enter a ticker to begin</p>
      <input
        type="text"
        placeholder="e.g. AAPL"
        aria-label="Stock ticker symbol"
        className="w-full max-w-xs rounded-md border border-neutral-300 px-4 py-2 text-center text-sm uppercase tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500"
        readOnly
      />
    </div>
  );
}
