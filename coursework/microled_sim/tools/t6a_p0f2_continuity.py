#!/usr/bin/env python3
"""T6-A P0-F2：L1 连续场景重放（同一个寄存器实例，零 ModelSim）。

复审发现的缺口（P0-F）
----------------------
真实 L1 TB 在**同一颗 DUT** 上连续跑 E01–E22，而此前的软件模型按场景分段
（Phase S 一个实例、M 矢量另一个实例且手工置初值），于是 E18 遗留的
COMM_TO(bit7) 从未被带进 E21/E22——真实 TB 里 E21d（status 全零）与
E22（bit7 必须为 0）必然失败（复审 INDEPENDENT_L1_E18_TO_E22_REPLAY.csv）。

本工具把 E18 → E20（死时钟）→ E20a（一次合法 W1C 0x080 清理）→
E21a–d（多源确定性矢量）→ E22a–c（引脚独占）放在**同一个 Regs 实例**上
连续执行，规则与候选 RTL 一致：按位异步捕获、逐位组合 W1C 清除、旧值/NBA。

正控：E20 保持、E20a 清理且仍黑（未再使能）、E21d 全清、E22 总线 bit7 不置
COMM_TO、E22b 引脚触发、E22c 合法清。
负控（任务书 §B）：
  NC-PHASE  删掉 E20→E21 之间的共享 bit7 W1C → E21d/E22 真实 FAIL，残留 0x080；
  NC-REARM  把 E20a 的清除错误地当作再使能 → 检出 disp_armed=1 / hw_blank=0；
  NC-SOURCE 恢复总线 hw_fault[7] 误连 → E22 被击中；
  回归：D33/D53（原历史序列）与 P0-E M1–M4 在同一模型里仍 PASS。
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t6a_p0e_model import Regs, bring_up, ck          # noqa: E402

VIS = 0x080


def continuity(rows, fails, cleanup=True, neg=None, bus_bit7_leak=False,
               sink=None):
    """sink: 独立的失败收集器（负控运行用），None 则用调用方的 fails。"""
    if sink is None:
        sink = fails
    """同一实例连续重放 E18 → E20 → [E20a] → E21 → E22。

    bus_bit7_leak=True 模拟 NC-SOURCE：顶层仍把总线 bit7 OR 进 COMM_TO。
    cleanup=False 模拟 NC-PHASE：E20 与 E21 之间没有那笔 W1C。
    返回关键检查点的 (status, caught) 字典。
    """
    p = Regs(neg=neg)
    bring_up(p)                                  # E01 前的合法点亮
    snap = {}
    lck = lambda name, cond, clause: ck(name, cond, sink, clause)

    def emit(name, check, expected, clause, hw=0):
        rows.append(dict(step=name, hw_fault='%03X' % hw,
                         fs_old='%03X' % p.fault_status,
                         caught_old='%03X' % (p.caught if p.variant == 'per_source'
                                              else p.shared),
                         armed_old=p.disp_armed,
                         fs_new='%03X' % p.fault_status,
                         caught_new='%03X' % (p.caught if p.variant == 'per_source'
                                              else p.shared),
                         armed_new=p.disp_armed, hw_blank=p.hw_blank(hw),
                         check=check, expected=expected, clause=clause))

    # ---- E18：4 ns 引脚脉冲 + 读事务不清除 ----
    p.async_fault_edge(bit=7)
    p.edge(hw_fault=0)                           # 脉冲后的沿
    emit('E18 pulse + read', 'E18_read_cannot_clear', 'bit7=1', 'C2/C3')
    snap['E18'] = (p.fault_status, p.caught if p.variant == 'per_source' else p.shared)
    lck('E18_read_cannot_clear', (p.fault_status & VIS) == VIS, 'C2/C3')

    # ---- E19/E20：死时钟，捕获保持 ----
    lck('E19_dark_with_a_dead_clock', p.hw_blank(0) == 1, 'C5')
    ck('E20_capture_survived_the_dead_clock',
       (p.caught & VIS) == VIS if p.variant == 'per_source' else p.shared == 1,
       fails, 'C5')
    emit('E19/E20 dead clock hold', 'E19/E20', 'capture holds', 'C5')

    # ---- E20a：一次合法 W1C 关闭 Phase S 边界 ----
    if cleanup:
        p.edge(hw_fault=0, w1c=VIS, fw=True)
        p.edge(hw_fault=0); p.edge(hw_fault=0)   # 邮箱完成的余沿
        emit('E20a W1C 0x080 cleanup', 'E20a_phase_s_cleanup_without_rearm',
             'status=0, caught=0, armed=0, dark', 'C3/C4')
        snap['E20a'] = (p.fault_status, p.caught if p.variant == 'per_source'
                        else p.shared)
        ck('E20a_phase_s_cleanup_without_rearm',
           (p.fault_status == 0) and
           ((p.caught == 0) if p.variant == 'per_source' else (p.shared == 0)) and
           (p.disp_armed == 0) and (p.hw_blank(0) == 1), fails, 'C3/C4')
    else:
        snap['E20a'] = (p.fault_status, p.caught if p.variant == 'per_source'
                        else p.shared)

    # ---- E21：多源确定性矢量（bit0 已恢复 + bit2 活）----
    p.edge(hw_fault=0x001)
    p.edge(hw_fault=0)
    lck('E21_pre_uvlo_latched', (p.visible_fault(0) & 0x001) == 0x001, 'C2')
    p.edge(hw_fault=0x004)                       # OT 活
    p.edge(hw_fault=0x004, w1c=0x001, fw=True)   # W1C 只覆盖 bit0
    ck('E21_multi_source_partial_clear',
       (p.visible_fault(0) & 0x001) == 0 and (p.visible_fault(0x004) & 0x004) == 0x004,
       fails, 'C3')
    for _ in range(30):
        p.edge(hw_fault=0x004)
    ck('E21b_cleared_cause_does_not_resurrect',
       (p.visible_fault(0) & 0x001) == 0, fails, 'C3')
    p.edge(hw_fault=0x004, w1c=0x004, fw=True)   # 活位不可清
    ck('E21c_live_bit2_cannot_clear',
       (p.visible_fault(0x004) & 0x004) == 0x004, fails, 'C3')
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=0x004, fw=True)
    emit('E21d all clear after release', 'E21d_all_clear_after_release',
         'status==0, capture==0', 'C3/C4')
    snap['E21d'] = (p.fault_status, p.caught if p.variant == 'per_source'
                    else p.shared)
    ck('E21d_all_clear_after_release',
       (p.fault_status == 0) and
       ((p.caught == 0) if p.variant == 'per_source' else (p.shared == 0)),
       fails, 'C3/C4')

    # ---- E22：COMM_TO 引脚独占 ----
    if bus_bit7_leak:
        p.edge(hw_fault=VIS)                     # NC-SOURCE：总线 bit7 误连
    else:
        p.edge(hw_fault=0)                       # 总线 bit7 被顶层掩掉
    ck('E22_bus_bit7_cannot_set_comm_to',
       (p.visible_fault(0) & VIS) == 0, fails, 'C2')
    p.async_fault_edge(bit=7)                    # 真正拉低引脚
    p.edge(hw_fault=0)
    lck('E22b_pin_pull_still_captures', (p.visible_fault(0) & VIS) == VIS, 'C2')
    p.edge(hw_fault=0, w1c=VIS, fw=True)
    p.edge(hw_fault=0)
    ck('E22c_pin_cause_clears_by_its_own_mask', (p.visible_fault(0) & VIS) == 0,
       fails, 'C3')
    emit('E22c pin cause cleared', 'E22c', 'bit7=0', 'C3')
    return snap


def main():
    fails = []
    rows = []
    print('=== T6-A P0-F2: L1 continuity replay on ONE register instance (zero ModelSim) ===')
    print()

    # ---------- 正控：连续 E18→E22，含 E20a 清理 ----------
    print('[positive] E18 -> E20 -> E20a -> E21 -> E22, same instance')
    snap = continuity(rows, fails, cleanup=True)
    ck('R-CONT_cleanup_closed_the_phase_boundary',
       snap['E20a'] == (0, 0) and snap['E21d'] == (0, 0), fails, 'C3/C4')
    print()

    # ---------- NC-PHASE：删掉清理写 → E21d/E22 真实 FAIL ----------
    print('[NC-PHASE] drop the E20a W1C: the E18 history must poison E21d/E22')
    scratch = []
    n1 = continuity(rows, scratch, cleanup=False)
    print('   after E21d: status=0x%03X caught=0x%03X'
          % (n1['E21d'][0], n1['E21d'][1]))
    ck('NC-PHASE no cleanup -> E21d sees the stale 0x080 (reviewer table)',
       (n1['E21d'][0] & VIS) == VIS, fails, 'C3')
    ck('NC-PHASEb no cleanup -> E22 cannot start from zero',
       (n1['E20a'][0] & VIS) == VIS, fails, 'C3')
    ck('NC-PHASEc the TB-level E21d/E22 assertions really FAIL without it',
       ('E21d_all_clear_after_release' in scratch) and
       ('E22_bus_bit7_cannot_set_comm_to' in scratch), fails, 'C3')

    # ---------- NC-REARM：把清理写误当再使能 ----------
    print('[NC-REARM] treating the cleanup write as a re-enable must be visible')
    n2 = Regs()
    bring_up(n2)
    n2.async_fault_edge(bit=7)
    n2.edge(hw_fault=0)
    n2.edge(hw_fault=0, w1c=VIS, fw=True)        # 合法清理
    n2.edge(hw_fault=0, ctrl=0b001, safe=1, ready=1)   # 缺陷版：顺手再使能
    print('   armed=%d blank=%d' % (n2.disp_armed, n2.hw_blank(0)))
    ck('NC-REARM a re-enable after cleanup IS accepted (so E20a must not do it)',
       (n2.disp_armed == 1) and (n2.hw_blank(0) == 0), fails, 'C4')

    # ---------- NC-SOURCE：总线 bit7 误连必须被 E22 击中 ----------
    print('[NC-SOURCE] restore the bus-bit7 leak: E22 must catch it')
    # E22 的"牙齿"证明：若总线 bit7 被误连（模型里等价于把它送进折叠输入），
    # COMM_TO 就会在 fault_n=1 时被锁存 —— 这正是真实 TB 的 E22 要拦的缺陷。
    n3 = Regs()
    bring_up(n3)
    n3.edge(hw_fault=VIS)                        # fault_n=1，但总线 bit7 误连
    n3.edge(hw_fault=0)
    ck('NC-SOURCE leaked bus bit7 latches COMM_TO (what E22 catches)',
       (n3.visible_fault(0) & VIS) == VIS, fails, 'C2')

    # ---------- 回归：D33/D53 与 M1–M4 在同一模型仍 PASS ----------
    print('[regression] legacy D33/D53 and the P0-E M vector on this model')
    g = Regs()
    g.edge(hw_fault=0x001); g.edge(hw_fault=0)
    g.edge(hw_fault=0, w1c=0x001, fw=True)
    g.edge(hw_fault=0x004); g.edge(hw_fault=0)
    g.edge(hw_fault=0, w1c=0x004, fw=True)
    ck('REG-D33_fault_register_clean', g.visible_fault(0) == 0, fails, 'C2/C3')
    g.edge(hw_fault=0x002); g.edge(hw_fault=0)
    g.edge(hw_fault=0, w1c=0x002, fw=True)
    g.edge(hw_fault=0, ctrl=0b001, safe=1, ready=1)
    ck('REG-D53_display_enabled_after_cleanup',
       (g.disp_armed == 1) and (g.hw_blank(0) == 0), fails, 'C4')
    m = Regs()
    m.fault_status = 0x005; m.caught = 0x005
    m.edge(hw_fault=0x004, w1c=0x001, fw=True)
    ck('REG-M1_per_bit_clear_while_ot_live',
       (m.fault_status == 0x004) and (m.caught == 0x004), fails, 'C3')
    print()

    # ---------- CSV ----------
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, '..', 't6a', 'E18_E22_CONTINUITY.csv')
    if not os.path.isdir(os.path.dirname(out)):
        out = os.path.join(here, 'E18_E22_CONTINUITY.csv')
    if rows:
        with open(out, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print('CSV written: %s (%d data rows)' % (os.path.normpath(out), len(rows)))
    print()

    print('--- not proven here ---')
    print('* state rules only: no RTL simulation; the L1 budget stays on HOLD')
    print()

    if fails:
        print('RESULT=FAIL (%s)' % ', '.join(fails))
        return 1
    print('RESULT=PASS  continuous E18->E22 closes with E20a; NC-PHASE/NC-REARM/')
    print('             NC-SOURCE all reproduce the reviewed failures; D33/D53/M hold')
    return 0


if __name__ == '__main__':
    sys.exit(main())
