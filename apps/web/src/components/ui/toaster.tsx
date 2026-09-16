// src/components/ui/toaster.tsx — toast notifications via react-hot-toast.
"use client";

import { Toaster as HotToaster } from "react-hot-toast";

export function Toaster() {
  return (
    <HotToaster
      position="bottom-right"
      toastOptions={{
        style: {
          background: "hsl(224 71% 8%)",
          color: "hsl(0 0% 90%)",
          border: "1px solid hsl(214 32% 20%)",
        },
        className: "border",
      }}
    />
  );
}
