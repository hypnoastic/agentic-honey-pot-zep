/* eslint-disable react/prop-types */
import { useState } from "react";

export default function LoginPage({ onLogin }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (response.ok) {
        onLogin();
      } else {
        setError(true);
      }
    } catch {
      setError(true);
    }
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black text-white">
      <div className="w-full max-w-md px-8 py-10 bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl">
        <h1 className="text-3xl font-bold mb-8 text-center tracking-tight">
          Access Control
        </h1>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-2 text-center">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setError(false);
              }}
              className="w-full px-4 py-5 bg-black border border-zinc-700 rounded-xl focus:border-white outline-none transition-colors text-3xl text-center font-bold tracking-widest"
              autoFocus
            />
          </div>

          {error && (
            <p className="text-red-500 text-sm text-center">
              Invalid access credentials.
            </p>
          )}

          <button
            type="submit"
            className="w-full py-3 bg-white text-black font-bold rounded-xl text-lg hover:bg-zinc-200 transition-colors"
          >
            Enter Dashboard
          </button>
        </form>
      </div>
    </div>
  );
}
