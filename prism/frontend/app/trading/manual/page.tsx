import { Suspense } from "react";
import BuilderClient from "../BuilderClient";

export default function ManualTradingPage() {
  return (
    <Suspense>
      <BuilderClient buildPath="manual" />
    </Suspense>
  );
}
