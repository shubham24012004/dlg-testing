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
        router.replace("/");
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
          className="rounded bg-red-600 px-4 py-2 cursor-pointer text-sm text-white hover:bg-red-700"
        >
          Logout
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border bg-white shadow">
        <table className="w-full table-fixed border-collapse text-sm">
          <thead className="bg-gray-100 text-gray-700">
            <tr>
              <th className="border-b px-4 py-3 text-left w-2/6">LSP Name</th>
              <th className="border-b px-4 py-3 text-right w-1/6">
                Total Amount (₹ Cr)
              </th>
              <th className="border-b px-4 py-3 text-center w-1/6">
                Total No. Of Portfolios
              </th>
              <th className="border-b px-4 py-3 text-center w-1/6">Status</th>
              <th className="border-b px-4 py-3 text-center w-1/6">
                As On Date
              </th>
              <th className="border-b px-4 py-3 text-center w-1/6">
                Last Crawl
              </th>
              <th className="border-b px-4 py-3 text-center w-1/6">Actions</th>
            </tr>
          </thead>

          <tbody>
            {rows.map((row) => (
              <tr key={row.lsp_id} className="text-gray-700 hover:bg-gray-50">
                <td className="border-b px-4 py-3 text-left truncate">
                  {row.name}
                </td>

                <td className="border-b px-4 py-3 text-right">
                  {row.total_amount.toLocaleString()}
                </td>

                <td className="border-b px-4 py-3 text-center">
                  {row.total_portfolios}
                </td>

                <td className="border-b px-4 py-3 text-center">
                  <span
                    className={`inline-block rounded-full px-3 py-1 text-xs font-medium ${
                      row.status === "Completed"
                        ? "bg-green-100 text-green-700"
                        : row.status === "Partial"
                          ? "bg-yellow-100 text-yellow-700"
                          : "bg-red-100 text-red-700"
                    }`}
                  >
                    {row.status}
                  </span>
                </td>

                <td className="border-b px-4 py-3 text-center">
                  {row.as_on_year && row.as_on_month
                    ? new Date(
                        row.as_on_year,
                        row.as_on_month,
                        0,
                      ).toLocaleDateString("en-GB")
                    : "-"}
                </td>

                <td className="border-b px-4 py-3 text-center">
                  {row.last_crawl_date
                    ? new Date(row.last_crawl_date).toLocaleDateString("en-GB")
                    : "-"}
                </td>

                <td className="border-b px-4 py-3 text-center">
                  <button
                    onClick={() => router.push(`/dashboard/${row.lsp_id}`)}
                    className="text-sm font-medium text-blue-600 hover:underline cursor-pointer"
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