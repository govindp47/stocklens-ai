"use client";

/**
 * SettingsModal — OpenAI API key configuration.
 *
 * Security:
 * - Input is type="password" and autoComplete="off".
 * - Never pre-populated from the store (key is write-only in UI).
 * - No localStorage write occurs anywhere.
 * - Key lives in Zustand in-memory state only — cleared on page refresh.
 */

import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Settings,
  X,
  CheckCircle2,
  AlertCircle,
  KeyRound,
  Cpu,
} from "lucide-react";
import { useSettingsStore } from "@/store";

export function SettingsModal() {
  const { openAiKeyStatus, activeModel, setOpenAiKey, clearOpenAiKey } =
    useSettingsStore();

  const [inputValue, setInputValue] = useState("");
  const [open, setOpen] = useState(false);

  function handleSave() {
    const trimmed = inputValue.trim();
    if (!trimmed.startsWith("sk-")) return;
    setOpenAiKey(trimmed);
    setInputValue("");
    setOpen(false);
  }

  function handleClear() {
    clearOpenAiKey();
    setInputValue("");
  }

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) setInputValue("");
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Trigger asChild>
        <button
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-xs font-medium text-muted-foreground
            shadow-panel hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
          data-testid="settings-button"
          aria-label="Open settings"
        >
          <Settings className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Settings</span>
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2
            rounded-2xl bg-surface shadow-2xl focus:outline-none animate-fade-in-up"
          aria-describedby="settings-description"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <Dialog.Title className="text-sm font-semibold text-foreground">
              Settings
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground
                  hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
                aria-label="Close settings"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>

          <div id="settings-description" className="px-5 py-5 space-y-5">
            {/* Current model */}
            <div className="flex items-center gap-2.5 rounded-lg border border-border bg-muted/50 px-3 py-2.5">
              <Cpu
                className="h-4 w-4 text-brand-500 shrink-0"
                aria-hidden="true"
              />
              <div>
                <p className="text-[11px] text-muted-foreground">
                  Current model
                </p>
                <p className="text-xs font-semibold text-foreground">
                  {activeModel}
                </p>
              </div>
            </div>

            {/* OpenAI key section */}
            <div className="space-y-2">
              <label
                htmlFor="openai-key"
                className="flex items-center gap-1.5 text-xs font-medium text-foreground"
              >
                <KeyRound
                  className="h-3.5 w-3.5 text-muted-foreground"
                  aria-hidden="true"
                />
                OpenAI API Key
                <span className="font-normal text-muted-foreground">
                  (optional)
                </span>
              </label>
              <input
                id="openai-key"
                type="password"
                autoComplete="off"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSave()}
                placeholder="sk-..."
                className="w-full h-10 rounded-lg border border-border bg-surface px-3 text-sm
                  focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors placeholder:text-muted-foreground"
                data-testid="openai-key-input"
              />
            </div>

            {/* Status messages */}
            {openAiKeyStatus === "set" && (
              <div className="flex items-center gap-2 rounded-lg bg-green-50 border border-green-200 px-3 py-2">
                <CheckCircle2
                  className="h-3.5 w-3.5 text-green-600 shrink-0"
                  aria-hidden="true"
                />
                <p className="text-xs text-green-800">
                  API key active for this session
                </p>
              </div>
            )}
            {openAiKeyStatus === "invalid" && (
              <div
                role="alert"
                className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2"
              >
                <AlertCircle
                  className="h-3.5 w-3.5 text-red-600 shrink-0"
                  aria-hidden="true"
                />
                <p className="text-xs text-red-800">
                  Key rejected — analysis used local model instead
                </p>
              </div>
            )}

            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Your API key is used only for this session and is never stored or
              transmitted elsewhere.
            </p>

            {/* Buttons */}
            <div className="flex gap-2 pt-1">
              <button
                onClick={handleSave}
                disabled={!inputValue.trim()}
                className="flex-1 h-10 rounded-lg bg-brand-500 text-sm font-semibold text-white
                  hover:bg-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2
                  disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                data-testid="save-key-button"
              >
                Save
              </button>
              {openAiKeyStatus === "set" && (
                <button
                  onClick={handleClear}
                  className="h-10 rounded-lg border border-border bg-surface px-4 text-sm font-medium text-muted-foreground
                    hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
