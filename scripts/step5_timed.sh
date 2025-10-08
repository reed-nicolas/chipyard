#!/usr/bin/env bash
# scripts/step5_timed.sh
# Defines: chipyard_step5_timed_baseline
# This script assumes begin_step/exit_if_last_command_failed and $CYDIR are available from build-setup.sh

chipyard_step5_timed_baseline() {
  # Baseline = incremental compile (no clean), timed for chipyard and tapeout
  pushd "$CYDIR/sims/verilator" >/dev/null

  /usr/bin/time -f 'timing: step=5 mode=baseline target=chipyard status=OK real_seconds=%e real_hms=%E user_cpu_seconds=%U sys_cpu_seconds=%S cpu_pct=%P' \
    make launch-sbt SBT_COMMAND=";project chipyard; compile"

  /usr/bin/time -f 'timing: step=5 mode=baseline target=tapeout  status=OK real_seconds=%e real_hms=%E user_cpu_seconds=%U sys_cpu_seconds=%S cpu_pct=%P' \
    make launch-sbt SBT_COMMAND=";project tapeout; compile"

  popd >/dev/null

  # Print a formatted summary table from the current build-setup.log
  # This computes norm_serial_s = (user+sys) / round((user+sys)/real), with a floor of 1
  echo
  echo "========== Step 5 timing summary =========="
  grep -a -o 'timing: step=5 [^[:cntrl:]]*' "$CYDIR/build-setup.log" \
  | awk 'BEGIN{
      printf "%-9s %-8s %-6s %-10s %-10s %-10s %-7s %-16s\n",
             "mode","target","stat","real_s","user_s","sys_s","cpu%","norm_serial_s"
    }{
      for(i=1;i<=NF;i++){
        split($i,a,"=");
        if(a[1]=="mode") m=a[2];
        if(a[1]=="target") t=a[2];
        if(a[1]=="status") st=a[2];
        if(a[1]=="real_seconds") r=a[2];
        if(a[1]=="user_cpu_seconds") u=a[2];
        if(a[1]=="sys_cpu_seconds")  s=a[2];
        if(a[1]=="cpu_pct") p=a[2];
      }
      # compute normalized single-core time
      ru = (u+0); ss = (s+0); rr = (r+0);
      cpu_factor = (rr>0)? (ru+ss)/rr : 0;
      est = int(cpu_factor + 0.5); if(est < 1) est = 1;
      norm = (ru+ss)/est;
      printf "%-9s %-8s %-6s %-10s %-10s %-10s %-7s %-16.2f\n", m,t,st,r,u,s,p,norm;
    }'
  echo "==========================================="
}
