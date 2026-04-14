import { DISCLAIMER_TEXT } from "@/lib/constants";

export function Disclaimer() {
  return (
    <div
      role="banner"
      data-testid="disclaimer"
      className="w-full bg-amber-50 border-b border-amber-200 px-4 py-2 text-xs text-amber-800 text-center"
    >
      {DISCLAIMER_TEXT}
    </div>
  );
}
