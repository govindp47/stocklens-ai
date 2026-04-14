"use client";

/**
 * ModelSelector — modern AI-style provider + model picker.
 *
 * Shows a pill button with the active provider/model.
 * Opens a modal with two provider cards:
 *   • Ollama (Local · Free) — default, no API key needed
 *   • OpenAI — reveals API key input when selected
 *
 * Security: API key is type="password", never pre-populated, in-memory only.
 */

import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Cpu,
  KeyRound,
  X,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  Zap,
  Globe,
} from "lucide-react";
import { useSettingsStore } from "@/store";
import type { ModelProvider } from "@/store/settingsSlice";

// ─── Provider card data ───────────────────────────────────────────────────────

const PROVIDERS: {
  id: ModelProvider;
  name: string;
  subtitle: string;
  badge: string;
  badgeColor: string;
  icon: React.ElementType;
  models: string[];
}[] = [
  {
    id: "nvidia-llama",
    name: "NVIDIA Llama 3.1",
    subtitle: "Fast hosted inference (free tier)",
    badge: "Free · Cloud",
    badgeColor:
      "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800/60",
    icon: Zap,
    models: ["meta/llama-3.1-8b-instruct"],
  },
  {
    id: "nvidia-mistral",
    name: "NVIDIA Mistral 7B",
    subtitle: "Fast hosted inference (free tier)",
    badge: "Free · Cloud",
    badgeColor:
      "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800/60",
    icon: Zap,
    models: ["mistralai/mistral-7b-instruct-v0.3"],
  },
  {
    id: "nvidia-deepseek",
    name: "NVIDIA DeepSeek R1 Distill",
    subtitle: "Reasoning-optimized model (free tier)",
    badge: "Free · Cloud",
    badgeColor:
      "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800/60",
    icon: Zap,
    models: ["deepseek-ai/deepseek-r1-distill-llama-8b"],
  },
  {
    id: "ollama",
    name: "Ollama",
    subtitle: "Runs locally on your machine — no API key required",
    badge: "Free · Local",
    badgeColor:
      "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800/60",
    icon: Cpu,
    models: ["mistral:7b-instruct", "llama3:8b", "phi3:mini", "gemma2:9b"],
  },
  {
    id: "openai",
    name: "OpenAI",
    subtitle: "GPT-4o mini or GPT-4o via the OpenAI API",
    badge: "API Key Required",
    badgeColor:
      "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950/40 dark:text-violet-400 dark:border-violet-800/60",
    icon: Globe,
    models: ["gpt-4o-mini", "gpt-4o"],
  },
];

// ─── Provider card ────────────────────────────────────────────────────────────

function ProviderCard({
  provider,
  isSelected,
  onSelect,
}: {
  provider: (typeof PROVIDERS)[0];
  isSelected: boolean;
  onSelect: () => void;
}) {
  const Icon = provider.icon;
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full text-left rounded-xl border-2 p-4 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-brand-500
        ${
          isSelected
            ? "border-brand-500 bg-brand-50 shadow-glow-brand dark:bg-brand-50/5"
            : "border-border bg-surface hover:border-brand-200 hover:bg-muted/40"
        }`}
      aria-pressed={isSelected}
    >
      <div className="flex items-start gap-3">
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors ${
            isSelected
              ? "bg-brand-500 text-white"
              : "bg-muted text-muted-foreground"
          }`}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-foreground">
              {provider.name}
            </span>
            <span
              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${provider.badgeColor}`}
            >
              {provider.badge}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">
            {provider.subtitle}
          </p>
        </div>
        {/* Radio indicator */}
        <div
          className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 transition-all ${
            isSelected
              ? "border-brand-500 bg-brand-500"
              : "border-border bg-surface"
          }`}
        >
          {isSelected && <div className="h-1.5 w-1.5 rounded-full bg-white" />}
        </div>
      </div>
    </button>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function ModelSelector() {
  const {
    openAiKeyStatus,
    activeModel,
    selectedProvider,
    setOpenAiKey,
    clearOpenAiKey,
    setProvider,
  } = useSettingsStore();

  const [open, setOpen] = useState(false);
  const [pendingProvider, setPendingProvider] =
    useState<ModelProvider>(selectedProvider);
  const [pendingModel, setPendingModel] = useState(activeModel);
  const [keyInput, setKeyInput] = useState("");

  function handleOpen(nextOpen: boolean) {
    if (nextOpen) {
      setPendingProvider(selectedProvider);
      setPendingModel(activeModel);
      setKeyInput("");
    }
    setOpen(nextOpen);
  }

  function handleProviderSelect(id: ModelProvider) {
    setPendingProvider(id);
    const provider = PROVIDERS.find((p) => p.id === id)!;
    setPendingModel(provider.models[0]);
    setKeyInput("");
  }

  function handleSave() {
    setProvider(pendingProvider);
    if (pendingProvider === "openai" && keyInput.trim().startsWith("sk-")) {
      setOpenAiKey(keyInput.trim());
    } else if (pendingProvider !== "openai") {
      clearOpenAiKey();
    }
    setOpen(false);
  }

  const currentProviderMeta = PROVIDERS.find((p) => p.id === selectedProvider)!;
  const providerModels = PROVIDERS.find(
    (p) => p.id === pendingProvider,
  )!.models;
  const canSave =
    pendingProvider !== "openai" ||
    (pendingProvider === "openai" &&
      (keyInput.trim().startsWith("sk-") || openAiKeyStatus === "set"));

  return (
    <Dialog.Root open={open} onOpenChange={handleOpen}>
      {/* ── Trigger pill ──────────────────────────────────────────────────── */}
      <Dialog.Trigger asChild>
        <button
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5
            text-xs font-medium text-muted-foreground shadow-xs
            hover:border-brand-200 hover:text-foreground hover:bg-muted
            focus:outline-none focus:ring-2 focus:ring-brand-500 transition-all duration-150"
          aria-label="Change AI model"
        >
          <Zap className="h-3 w-3 text-brand-500 shrink-0" aria-hidden="true" />
          <span className="hidden sm:inline text-muted-foreground">
            {currentProviderMeta.name}
          </span>
          <span className="hidden sm:inline text-muted-foreground/50">·</span>
          <span className="font-mono text-foreground">{activeModel}</span>
          <ChevronDown
            className="h-3 w-3 shrink-0 text-muted-foreground/60"
            aria-hidden="true"
          />
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          aria-describedby="model-selector-desc"
        >
          <div
            className="w-full max-w-md rounded-2xl bg-surface border border-border
          shadow-2xl focus:outline-none animate-fade-in-up overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <Dialog.Title className="text-sm font-semibold text-foreground">
                  AI Model
                </Dialog.Title>
                <p
                  id="model-selector-desc"
                  className="text-xs text-muted-foreground mt-0.5"
                >
                  Choose the provider powering your analysis
                </p>
              </div>
              <Dialog.Close asChild>
                <button
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground
                    hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </Dialog.Close>
            </div>

            <div className="px-5 py-5 space-y-4">
              {/* Provider cards */}
              <div
                className="space-y-2.5"
                role="radiogroup"
                aria-label="AI provider"
              >
                {PROVIDERS.map((p) => (
                  <ProviderCard
                    key={p.id}
                    provider={p}
                    isSelected={pendingProvider === p.id}
                    onSelect={() => handleProviderSelect(p.id)}
                  />
                ))}
              </div>

              {/* Model picker */}
              <div className="space-y-1.5">
                <label
                  htmlFor="model-select"
                  className="text-xs font-medium text-foreground"
                >
                  Model
                </label>
                <select
                  id="model-select"
                  value={pendingModel}
                  onChange={(e) => setPendingModel(e.target.value)}
                  className="w-full h-9 rounded-lg border border-border bg-surface px-3 text-sm text-foreground
                    focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors appearance-none
                    bg-[url('data:image/svg+xml;charset=utf-8,<svg xmlns=%22http://www.w3.org/2000/svg%22 fill=%22none%22 viewBox=%220 0 20 20%22><path stroke=%22%236b7280%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22 stroke-width=%221.5%22 d=%22M6 8l4 4 4-4%22/></svg>')]
                    bg-[position:right_0.5rem_center] bg-no-repeat pr-8"
                >
                  {providerModels.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>

              {/* OpenAI API key section — only shown when OpenAI is selected */}
              {pendingProvider === "openai" && (
                <div className="space-y-2 animate-fade-in-up">
                  <label
                    htmlFor="openai-key-input"
                    className="flex items-center gap-1.5 text-xs font-medium text-foreground"
                  >
                    <KeyRound
                      className="h-3.5 w-3.5 text-muted-foreground"
                      aria-hidden="true"
                    />
                    OpenAI API Key
                  </label>
                  <input
                    id="openai-key-input"
                    type="password"
                    autoComplete="off"
                    value={keyInput}
                    onChange={(e) => setKeyInput(e.target.value)}
                    onKeyDown={(e) =>
                      e.key === "Enter" && canSave && handleSave()
                    }
                    placeholder={
                      openAiKeyStatus === "set"
                        ? "••••••••••••  (key active)"
                        : "sk-…"
                    }
                    className="w-full h-10 rounded-lg border border-border bg-surface px-3 text-sm font-mono
                      focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors placeholder:text-muted-foreground placeholder:font-sans"
                  />
                  {/* Status feedback */}
                  {openAiKeyStatus === "set" && !keyInput && (
                    <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 dark:bg-emerald-950/30 dark:border-emerald-800/50">
                      <CheckCircle2
                        className="h-3.5 w-3.5 text-emerald-600 shrink-0 dark:text-emerald-400"
                        aria-hidden="true"
                      />
                      <p className="text-xs text-emerald-800 dark:text-emerald-300">
                        API key active for this session
                      </p>
                    </div>
                  )}
                  {openAiKeyStatus === "invalid" && (
                    <div
                      role="alert"
                      className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2 dark:bg-red-950/30 dark:border-red-800/50"
                    >
                      <AlertCircle
                        className="h-3.5 w-3.5 text-red-600 shrink-0 dark:text-red-400"
                        aria-hidden="true"
                      />
                      <p className="text-xs text-red-800 dark:text-red-300">
                        Key was rejected — enter a valid key
                      </p>
                    </div>
                  )}
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    Your key is used only for this browser session and is never
                    stored or transmitted elsewhere.
                  </p>
                </div>
              )}

              {/* Save button */}
              <div className="flex gap-2 pt-2 border-t border-border">
                <button
                  onClick={handleSave}
                  disabled={!canSave}
                  className="flex-1 h-10 rounded-xl bg-brand-500 text-sm font-semibold text-white
                    hover:bg-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2
                    disabled:opacity-40 disabled:cursor-not-allowed transition-colors mt-1"
                >
                  Apply
                </button>
                {openAiKeyStatus === "set" && selectedProvider === "openai" && (
                  <button
                    onClick={() => {
                      clearOpenAiKey();
                      setOpen(false);
                    }}
                    className="h-10 rounded-xl border border-border bg-surface px-4 text-sm font-medium text-muted-foreground
                      hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors mt-1"
                  >
                    Clear key
                  </button>
                )}
              </div>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
