"use client";  // Đánh dấu là Client Component

import { useEffect, useState } from "react";

// Giả sử useUser, useAuthModal, useSignerStatus, useLogout, useSigner là các hooks tùy chỉnh đã được định nghĩa
function useUser() {
  // Giả sử hook lấy thông tin người dùng
  return { orgId: "some-org-id" }; // Ví dụ, bạn có thể thay đổi theo logic của bạn
}

function useAuthModal() {
  // Giả sử hook để mở modal đăng nhập
  return { openAuthModal: () => console.log("Open auth modal") };
}

function useSignerStatus() {
  // Giả sử hook trạng thái signer
  return { isInitializing: false, isConnected: true };
}

function useLogout() {
  // Giả sử hook logout
  return { logout: () => console.log("Logging out") };
}

function useSigner() {
  // Giả sử hook signer
  return { inner: { stampWhoami: async () => "whoami-stamp", experimental_createApiKey: async () => {} } };
}

export default function Home() {
  const user = useUser();
  const { openAuthModal } = useAuthModal();
  const signerStatus = useSignerStatus();
  const { logout } = useLogout();
  const signer = useSigner();

  const [createdApiKey, setCreatedApiKey] = useState(false);

  // 🆕 Thêm đoạn này để tự động mở modal nếu chưa đăng nhập
  useEffect(() => {
    if (!user && !signerStatus.isInitializing) {
      openAuthModal();
    }
  }, [user, signerStatus.isInitializing]);

  useEffect(() => {
    // User logged out, so reset the state.
    if (!user && createdApiKey) {
      setCreatedApiKey(false);
    }
    // Waiting for user to be logged in.
    if (!user || !signer || !signerStatus.isConnected || createdApiKey) {
      return;
    }

    const submitStamp = async () => {
      const whoamiStamp = await signer.inner.stampWhoami();
      const resp = await fetch("/api/get-api-key", {
        method: "POST",
        body: JSON.stringify({ whoamiStamp }),
      });
      return (await resp.json()) as { publicKey: string };
    };

    const createApiKey = async (publicKey: string) => {
      await signer.inner.experimental_createApiKey({
        name: `server-signer-${new Date().getTime()}`,
        publicKey,
        expirationSec: 60 * 60 * 24 * 62, // 62 days
      });
    };

    const handleAll = async () => {
      const { publicKey } = await submitStamp();
      await createApiKey(publicKey);
      await fetch("/api/set-api-key-activated", {
        method: "POST",
        body: JSON.stringify({ orgId: user.orgId, apiKey: publicKey }),
      });
      setCreatedApiKey(true);
    };

    handleAll().catch((err) => {
      console.error(err);
      alert("Something went wrong. Please check the console for details.");
    });
  }, [createdApiKey, signer, signerStatus.isConnected, user]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      if (typeof window.crypto.subtle !== "object") {
        throw new Error("window.crypto.subtle is not available");
      }
    } catch (err) {
      alert(
        "Crypto API is not available in browser. Please be sure that the app is being accessed via localhost or a secure connection.",
      );
    }
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center gap-4 justify-center text-center">
      {signerStatus.isInitializing || (user && !createdApiKey) ? (
        <>Loading...</>
      ) : user ? (
        <div className="card">
          <div className="flex flex-col gap-2 p-2">
            <p className="text-xl font-bold">
              YOU ARE SUCCESSFULLY LOGGED IN TO THE GENSYN TESTNET
            </p>
            <button className="btn btn-primary mt-6" onClick={() => logout()}>
              Log out
            </button>
          </div>
        </div>
      ) : (
        <div className="card">
          <p className="text-xl font-bold">LOGIN TO THE GENSYN TESTNET</p>
          <div className="flex flex-col gap-2 p-2">
            <button className="btn btn-primary mt-6" onClick={openAuthModal}>
              Login
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
