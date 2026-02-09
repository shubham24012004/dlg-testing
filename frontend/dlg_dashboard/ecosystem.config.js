module.exports = {
  apps: [
    {
      name: "dlg-frontend",
      // run Next.js directly with node to avoid npm.cmd parsing issues on Windows
      script: "node",
      args: "node_modules/next/dist/bin/next start -p 8570 -H 0.0.0.0",
      cwd: "D:/DLG Analysis/dlg-analysis/frontend/dlg_dashboard",
      env: {
        PORT: "8570",
        HOST: "0.0.0.0",
        NEXT_PUBLIC_API_URL: ""
      }
    }
  ]
};
