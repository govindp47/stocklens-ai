'use client';

/**
 * SettingsModal — OpenAI API key configuration.
 *
 * Security constraints (per Section 3.13 of 05_APPLICATION_STRUCTURE.md):
 * - Input is type="password" and autoComplete="off" — never shown in plain text.
 * - The input is NEVER pre-populated from the store (key is write-only in UI).
 * - No localStorage write occurs anywhere in this component or its store slice.
 * - The key lives in Zustand in-memory state only — cleared on page refresh.
 *
 * Focus management: handled automatically by Radix Dialog (focus trap + aria-modal).
 */

import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Settings, X } from 'lucide-react';
import { useSettingsStore } from '@/store';

export function SettingsModal() {
  const { openAiKeyStatus, setOpenAiKey, clearOpenAiKey } = useSettingsStore();

  // Local input state — intentionally separate from the store value
  const [inputValue, setInputValue] = useState('');
  const [open, setOpen] = useState(false);

  function handleSave() {
    const trimmed = inputValue.trim();
    if (!trimmed.startsWith('sk-')) {
      return; // basic format guard — not a security check
    }
    setOpenAiKey(trimmed);
    setInputValue('');  // clear local input after save
    setOpen(false);
  }

  function handleClear() {
    clearOpenAiKey();
    setInputValue('');
  }

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) {
      setInputValue(''); // clear draft on close
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Trigger asChild>
        <button
          className="inline-flex min-h-[44px] min-w-[44px] items-center gap-1.5 rounded-md border border-neutral-200 bg-white px-3 py-2 text-xs font-medium text-neutral-600 shadow-sm hover:bg-neutral-50 focus:outline-none focus:ring-2 focus:ring-brand-500"
          data-testid="settings-button"
          aria-label="Open settings"
        >
          <Settings className="w-4 h-4" aria-hidden="true" />
          <span>Settings</span>
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        {/* Overlay */}
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-40" />

        {/* Content */}
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl focus:outline-none"
          aria-describedby="settings-description"
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="text-base font-semibold text-neutral-900">
              Settings
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                className="rounded p-1 text-neutral-400 hover:text-neutral-600 min-h-[44px] min-w-[44px] flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-brand-500"
                aria-label="Close settings"
              >
                <X className="w-4 h-4" aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>

          <div id="settings-description" className="space-y-4">
            {/* OpenAI key input */}
            <div>
              <label
                htmlFor="openai-key"
                className="block text-sm font-medium text-neutral-700 mb-1.5"
              >
                OpenAI API Key
                <span className="ml-1 text-xs font-normal text-neutral-400">
                  (optional)
                </span>
              </label>
              <input
                id="openai-key"
                type="password"
                autoComplete="off"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                placeholder="sk-..."
                className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                data-testid="openai-key-input"
              />
            </div>

            {/* Status messages */}
            {openAiKeyStatus === 'set' && (
              <p className="text-xs text-green-700">
                ✓ API key is active for this session
              </p>
            )}
            {openAiKeyStatus === 'invalid' && (
              <p role="alert" className="text-xs text-red-600">
                ✗ API key was rejected. Analysis used the local model instead.
              </p>
            )}

            {/* Session-only disclosure */}
            <p className="text-xs text-neutral-500">
              Your key is used only for this browser session and is{' '}
              <strong>never stored</strong> to disk or localStorage.
              Refreshing the page will clear it.
            </p>

            {/* Action buttons */}
            <div className="flex gap-2 pt-1">
              <button
                onClick={handleSave}
                disabled={!inputValue.trim()}
                className="flex-1 min-h-[44px] rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                data-testid="save-key-button"
              >
                Save
              </button>
              {openAiKeyStatus === 'set' && (
                <button
                  onClick={handleClear}
                  className="min-h-[44px] rounded-md border border-neutral-200 px-4 py-2 text-sm font-medium text-neutral-600 hover:bg-neutral-50 focus:outline-none focus:ring-2 focus:ring-brand-500"
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
