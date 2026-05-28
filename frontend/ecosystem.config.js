// PM2 cluster mode config for axis-frontend (Next.js 14)
// Usage: pm2 start ecosystem.config.js --env production

module.exports = {
  apps: [
    {
      name: 'axis-frontend',
      script: 'node_modules/.bin/next',
      args: 'start',
      cwd: '/home/axisai/axis-frontend',
      instances: 'max',         // cluster mode — one process per CPU core
      exec_mode: 'cluster',
      watch: false,
      max_memory_restart: '512M',
      env: {
        NODE_ENV: 'development',
        PORT: 3000,
      },
      env_production: {
        NODE_ENV: 'production',
        PORT: 3000,
        // IMPORTANT: Set all secrets in /home/axisai/axis-frontend/.env.local
        // Do NOT hard-code secrets here — PM2 logs are readable by other processes
      },
      log_file: '/home/axisai/logs/axis-frontend.log',
      error_file: '/home/axisai/logs/axis-frontend-error.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      restart_delay: 3000,
      max_restarts: 10,
    },
  ],
};
