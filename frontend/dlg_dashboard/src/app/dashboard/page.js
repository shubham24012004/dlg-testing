"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const handleLogout = () => {
    localStorage.removeItem("token");
    router.replace("/");
  };

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await api.get("/api/dashboard/lsp_summary");
        setRows(res.data.data.result);
      } catch (err) {
        router.replace("/login");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-600 text-sm">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-semibold text-gray-800">LSP Dashboard</h2>

        <button
          onClick={handleLogout}
          className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
        >
          Logout
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border bg-white shadow">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-gray-100 text-left text-sm font-semibold text-gray-700">
              <th className="border-b px-4 py-3">LSP Name</th>
              <th className="border-b px-4 py-3">Total Amount</th>
              <th className="border-b px-4 py-3">Portfolios</th>
              <th className="border-b px-4 py-3">Status</th>
              <th className="border-b px-4 py-3">Last Crawl</th>
              <th className="border-b px-4 py-3">Actions</th>
            </tr>
          </thead>

          <tbody>
            {rows.map((row) => (
              <tr
                key={row.lsp_id}
                className="text-sm text-gray-700 hover:bg-gray-50"
              >
                <td className="border-b px-4 py-3">{row.name}</td>

                <td className="border-b px-4 py-3">
                  ₹ {row.total_amount.toLocaleString()}
                </td>

                <td className="border-b px-4 py-3">{row.total_portfolios}</td>

                <td className="border-b px-4 py-3">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-medium ${
                      row.status === "COMPLETED"
                        ? "bg-green-100 text-green-700"
                        : row.status === "PARTIAL"
                          ? "bg-yellow-100 text-yellow-700"
                          : "bg-red-100 text-red-700"
                    }`}
                  >
                    {row.status}
                  </span>
                </td>

                <td className="border-b px-4 py-3">
                  {row.last_crawl_date
                    ? new Date(row.last_crawl_date).toLocaleDateString()
                    : "-"}
                </td>
                <td className="border-b px-4 py-3">
                  <button
                    onClick={() => router.push(`/dashboard/${row.lsp_id}`)}
                    className="text-sm text-blue-600 hover:underline"
                  >
                    View Details
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {rows.length === 0 ? (
          <div className="p-6 text-center text-gray-500">
            No LSP records found
          </div>
        ) : null}
      </div>
    </div>
  );
}
