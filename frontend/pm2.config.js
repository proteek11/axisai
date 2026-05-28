// PM2 Ecosystem Config — Axis AI Frontend (Next.js)
// Usage: pm2 start pm2.config.js --env production
module.exports = {
  apps: [
    {
      name: 'axis-frontend',
      script: 'node_modules/.bin/next',
      args: 'start -p 3000',
      cwd: __dirname,
      instances: 1,
      exec_mode: 'fork',
      watch: false,
      max_memory_restart: '512M',
      env: {
        NODE_ENV: 'development',
        PORT: 3000,
      },
      env_production: {
        NODE_ENV: 'production',
        PORT: 3000,
      },
      // Graceful restart — wait for old connections to drain
      kill_timeout: 5000,
      wait_ready: true,
      listen_timeout: 10000,
      // Auto-restart on crash
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
      // Log config
      error_file: '/var/log/axis-frontend/error.log',
      out_file: '/var/log/axis-frontend/out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,
    },
  ],
};
