'use client';

import React, { useState } from 'react';
import HeaderNav from '@/components/HeaderNav';

interface Citation {
  source: string;
  text: string;
}

interface Output {
  query: string;
  response: string;
  citations: Citation[];
}

// Basic HTML sanitizer to remove scripts and dangerous attributes.
// For production use, prefer a library like DOMPurify.
const sanitizeHtml = (html: string) => {
  if (!html) return '';
  // remove script tags and their content
  let s = html.replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '');
  // remove inline event handlers like onclick="..."
  s = s.replace(/on[a-z]+\s*=\s*"[^"]*"/gi, '');
  s = s.replace(/on[a-z]+\s*=\s*'[^']*'/gi, '');
  // neutralize javascript: pseudo-protocol in href/src attributes
  s = s.replace(/href\s*=\s*"javascript:[^"]*"/gi, 'href="#"');
  s = s.replace(/href\s*=\s*'javascript:[^']*'/gi, "href='#'");
  s = s.replace(/src\s*=\s*"javascript:[^"]*"/gi, '');
  s = s.replace(/src\s*=\s*'javascript:[^']*'/gi, '');
  return s;
};

export default function Page() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [output, setOutput] = useState<Output | null>(null);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setError(null);
    setOutput(null);

    if (!query.trim()) {
      setError('Please enter a query.');
      return;
    }

    setLoading(true);
    try {
      const base = (process.env.NEXT_PUBLIC_API_BASE as string) || 'http://localhost:8000';
      const url = `${base.replace(/\/$/, '')}/query?q=${encodeURIComponent(query)}`;
      const resp = await fetch(url);

      const contentType = resp.headers.get('content-type') || '';
      // If backend returned HTML, it's likely the request hit the frontend (Next) instead of the API.
      if (contentType.includes('text/html')) {
        const bodyText = await resp.text();
        const msg = `Received HTML response from ${url}. This usually means the frontend handled the request (404) or the backend is not running. Ensure the API is available at ${base}.`;
        // Log the HTML to console to aid debugging without showing huge HTML to users.
        console.debug('HTML response from /query:', bodyText.slice(0, 1000));
        throw new Error(msg);
      }

      if (!resp.ok) {
        let detail = await resp.text();
        try {
          if (contentType.includes('application/json')) {
            const j = await resp.json();
            detail = j.detail || JSON.stringify(j);
          }
        } catch (_) {}
        throw new Error(detail || `HTTP ${resp.status}`);
      }

      const data: Output = await resp.json();
      setOutput(data);
    } catch (err: any) {
      setError(err?.message || 'Unexpected error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <HeaderNav signOut={() => {}} />
      <main className="max-w-3xl mx-auto p-6">
        <h1 className="text-3xl font-semibold mb-4">Westeros Legal Assistant</h1>
        <p className="text-sm text-gray-600 mb-6">
          Ask a question about the laws and get a concise answer with section citations.
        </p>

        <form onSubmit={handleSubmit} className="flex gap-2 mb-4">
          <input
            className="flex-1 px-4 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            placeholder="Enter your question or keywords..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Enter query"
          />
          <button
            type="submit"
            className="px-4 py-2 bg-blue-600 text-white rounded-md disabled:opacity-60"
            disabled={loading}
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </form>

        {error && (
          <div className="mb-4 p-3 bg-red-50 text-red-800 rounded">{error}</div>
        )}

        {output && (
          <section className="space-y-4">
            <div className="p-4 bg-white rounded shadow-sm">
              <h2 className="text-xl font-medium mb-2">Answer</h2>
              <div className="whitespace-pre-wrap text-gray-800" dangerouslySetInnerHTML={{ __html: sanitizeHtml(output.response) }} />
            </div>

            <div className="p-4 bg-white rounded shadow-sm">
              <h3 className="text-lg font-medium mb-2">Citations</h3>
              <ul className="space-y-3">
                {output.citations.length === 0 && (
                  <li className="text-sm text-gray-600">No citations returned.</li>
                )}
                {output.citations.map((c, idx) => (
                  <li key={idx} className="p-3 border rounded">
                    <div className="text-sm text-blue-700 font-semibold">{c.source}</div>
                    <div className="mt-1 text-sm text-gray-700 whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: sanitizeHtml(c.text) }} />
                  </li>
                ))}
              </ul>
            </div>
          </section>
        )}

        <footer className="mt-8 text-xs text-gray-500">
          Results are generated from the indexed legal documents. If the service is not ready, the API will return a 503 error.
        </footer>
      </main>
    </div>
  );
}
