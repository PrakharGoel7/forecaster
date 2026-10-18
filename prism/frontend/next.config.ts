import type { NextConfig } from "next";

const renamedSampleHandles = [
  "mossyline", "cirrus", "pocketfuture", "civicsignal", "crosswinds",
  "ratecascade", "launchwatch", "moonwalks", "wellhead", "gridatlas",
  "fourthdown", "northbank", "iceorange", "iceblue", "thunderlane",
  "motorcity", "filmreel", "healthhorizon", "cupcounter", "stargazer",
];

const nextConfig: NextConfig = {
  redirects() {
    return renamedSampleHandles.map((handle) => ({
      source: `/users/demo_${handle}`,
      destination: `/users/${handle}`,
      permanent: true,
    }));
  },
};

export default nextConfig;
