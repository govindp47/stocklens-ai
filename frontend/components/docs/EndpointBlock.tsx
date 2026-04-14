/**
 * EndpointBlock — documents a single API endpoint.
 *
 * Renders: method badge, path, description, request/response schemas,
 * and at least one curl example.
 *
 * React Server Component — no 'use client' directive.
 */

import { CodeBlock } from "./CodeBlock";

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";

interface EndpointBlockProps {
  id?: string;
  method: HttpMethod;
  path: string;
  description: string;
  requestBody?: string;
  responseSchema: string;
  curlExample: string;
  notes?: string[];
}

const METHOD_COLORS: Record<HttpMethod, string> = {
  GET: "bg-blue-100 text-blue-800",
  POST: "bg-green-100 text-green-800",
  PUT: "bg-amber-100 text-amber-800",
  DELETE: "bg-red-100 text-red-800",
  PATCH: "bg-purple-100 text-purple-800",
};

export function EndpointBlock({
  id,
  method,
  path,
  description,
  requestBody,
  responseSchema,
  curlExample,
  notes,
}: EndpointBlockProps) {
  return (
    <section
      id={id}
      className="border border-neutral-200 rounded-lg overflow-hidden mb-6"
    >
      {/* Method + path header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-neutral-50 border-b border-neutral-200">
        <span
          className={`px-2 py-0.5 rounded text-xs font-bold font-mono ${METHOD_COLORS[method]}`}
        >
          {method}
        </span>
        <code className="text-sm font-mono text-neutral-800">{path}</code>
      </div>

      <div className="px-4 py-4 space-y-4">
        {/* Description */}
        <p className="text-sm text-neutral-700">{description}</p>

        {/* Notes */}
        {notes && notes.length > 0 && (
          <ul className="list-disc list-inside space-y-1">
            {notes.map((note, i) => (
              <li key={i} className="text-xs text-neutral-600">
                {note}
              </li>
            ))}
          </ul>
        )}

        {/* Request body */}
        {requestBody && (
          <div>
            <h4 className="text-xs font-semibold text-neutral-600 uppercase tracking-wide mb-1">
              Request Body
            </h4>
            <CodeBlock code={requestBody} language="json" />
          </div>
        )}

        {/* Response schema */}
        <div>
          <h4 className="text-xs font-semibold text-neutral-600 uppercase tracking-wide mb-1">
            Response
          </h4>
          <CodeBlock code={responseSchema} language="json" />
        </div>

        {/* curl example */}
        <div>
          <h4 className="text-xs font-semibold text-neutral-600 uppercase tracking-wide mb-1">
            Example
          </h4>
          <CodeBlock code={curlExample} language="bash" />
        </div>
      </div>
    </section>
  );
}
