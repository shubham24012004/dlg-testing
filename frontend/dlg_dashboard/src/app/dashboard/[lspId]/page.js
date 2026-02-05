"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import api from "@/lib/api";

export default function LspRawPage() {
  const { lspId } = useParams();
  const router = useRouter();

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchRawData = async () => {
      try {
        const res = await api.get("/api/dashboard/lsp_raw", {
          params: { lsp_id: lspId },
        });

        setRows(res.data.data.result);
      } catch (err) {
        router.replace("/login");
      } finally {
        setLoading(false);
      }
    };

    fetchRawData();
  }, [lspId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-600 text-sm">Loading dashboard...</div>
      </div>
    );
  }


  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {/* HEADER */}
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-semibold text-gray-800">
          LSP Raw Data (ID: {lspId})
        </h2>

        <button
          onClick={() => router.back()}
          className="rounded border bg-gray-500 hover:bg-gray-700 px-4 py-2 text-sm text-white"
        >
          ← Back
        </button>
      </div>

      {/* TABLE */}
      <div className="overflow-x-auto rounded-lg border bg-white shadow">
        <table className="w-full table-fixed border-collapse text-sm">
          <thead className="bg-gray-100 text-gray-700">
            <tr>
              <th className="border-b px-4 py-2 text-left w-1/5">Lender</th>
              <th className="border-b px-4 py-2 text-left w-1/5">Portfolio</th>
              <th className="border-b px-4 py-2 text-center w-1/6">
                Amount (₹ Cr)
              </th>
              <th className="border-b px-4 py-2 text-center w-1/6">
                As On Date
              </th>
              <th className="border-b px-4 py-2 text-center w-1/5">
                Scrape Date
              </th>
              <th className="border-b px-4 py-2 text-center w-1/6">Status</th>
            </tr>
          </thead>

          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx} className="hover:bg-gray-50 text-gray-700">
                <td className="border-b px-4 py-2 text-left truncate">
                  {row.lender || "-"}
                </td>

                <td className="border-b px-4 py-2 text-left truncate">
                  {row.portfolio || "-"}
                </td>

                <td className="border-b px-4 py-2 text-center">
                  {row.amount ? row.amount.toLocaleString() : "-"}
                </td>

                <td className="border-b px-4 py-2 text-center">
                  {row.as_on_timestamp
                    ? new Date(row.as_on_timestamp).toLocaleDateString()
                    : "-"}
                </td>

                <td className="border-b px-4 py-2 text-center">
                  {row.scrape_timestamp
                    ? new Date(row.scrape_timestamp).toLocaleString()
                    : "-"}
                </td>

                <td className="border-b px-4 py-2 text-center">
                  <span className="inline-block rounded bg-gray-200 px-3 py-1 text-xs">
                    {row.complete}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {rows.length === 0 && (
          <div className="p-6 text-center text-gray-500">
            No raw records found
          </div>
        )}
      </div>
    </div>
  );
}
