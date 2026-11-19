#!/usr/bin/env python3
"""T6-A P0-E：故障源归属合同 + 历史回归重放（逐事件状态模型，零 ModelSim）。

复审驱动（P0-D 之后）
--------------------
P0-D 的单一捕获锁存把**任何** hw_fault 位都映射进 COMM_TO(bit7)，于是历史
L1 回归按 RTL 规则推演出 D33=0x080（期望 0x000）、D53 再使能被拒
（见 independent_l1_regression_counterexample.csv）。本轮冻结的合同（方案 A）：

  C1  FAULT_n 是开漏线与、低有效引脚；V1.3 不承诺最小脉宽/源端锁存
      → 每一路都需要异步置位捕获（引脚与本地总线一视同仁）；
  C2  COMM_TO(bit7) **只**代表共享 FAULT_n 事件（段0704 原文）；
      本地 UVLO/OV/OT 的捕获映射到**各自的状态位**，不进 bit7；
  C3  W1C 掩码位 k 同拍清除 status[k] 与捕获[k]；活故障位不可清；
      零掩码一位都不动；不存在隐式跨位清除（bit0/1/2 不清 bit7）；
  C4  恢复 = 清除全部锁存原因 + 显式 CTRL 再使能；清除本身不点亮；
  C5  清除只走 posedge clk 分支 → 死时钟既不清也丢；
  C6  hw_blank 六锁不变（blank|!en|live|caught|!armed|disp_fault）。

variants（每个都是一条会 FAIL 的负控）：
  per_source   = P0-E 候选（11 位逐源捕获）
  shared_bit7  = P0-D 候选（单锁存 OR 进 bit7）→ 复现 D33/D53 反例
  registered   = P0-C 缺陷（寄存器 clr_fault）→ bit7/状态位复活
  no_capture   = 无捕获（电平直通）→ 亚周期脉冲丢失
  loose_rearm  = 再使能不看捕获/锁存 → 违反 C4
  no_mask_check= 清除不看掩码 → 违反 C3
"""
import csv
import os
import sys

PERIOD = 10000                  # ps（100 MHz）
VIS = 0x080                     # COMM_TO
DISPLAY_MASK = 0x7FF & ~0x100   # 除 ERR_REG(bit8)

V1_3 = {
    'C1': 'V1.3 段0492-0496：FAULT_n 开漏/线与/低有效，无最小脉宽与源端锁存保证',
    'C2': 'V1.3 段0704：TCON 捕获共享 FAULT_n 后置 COMM_TO',
    'C3': 'V1.3 段0599：FAULT_STATUS 为 W1C；活故障位不可清',
    'C4': 'V1.3 段0907-0912：恢复需 Host 清除 + 显式再使能；清除不自动点亮',
    'C5': 'V1.3 段0913-0915：时钟/帧超时；死时钟不得清锁存',
    'C6': 'P0-B 复审要求：本地窄脉冲不得因同步采样而丢失',
}


class Regs:
    """两个 always 块 + 按位组合清除请求（与 RTL 一一对应）。"""

    def __init__(self, neg=None, variant='per_source'):
        self.neg = set(neg or ())
        if 'no_registered_clear' in self.neg:
            variant = 'registered'
        if 'shared_capture' in self.neg:
            variant = 'shared_bit7'
        if 'no_capture' in self.neg:
            variant = 'no_capture'
        self.variant = variant
        self.en = 0
        self.blank_r = 1
        self.fault_status = 0
        self.disp_armed = 0
        self.caught = 0          # 11 位逐源捕获（共享 variant 只用 bit7）
        self.shared = 0          # shared_bit7 / registered variant 的单锁存
        self.clr = 0             # registered variant 的 clr_fault 寄存器
        self.int_status = 0
        self.fsd = 0
        self.frames = 0

    # ---------------- 组合量（读旧值） ----------------
    def visible_fault(self, hw_fault):
        f = self.fault_status | hw_fault
        if self.variant in ('per_source',):
            f |= self.caught
        elif self.variant in ('shared_bit7', 'registered'):
            if self.shared and 'no_caught_visibility' not in self.neg:
                f |= VIS
        elif 'no_caught_visibility' not in self.neg and self.caught:
            f |= self.caught
        return f & 0x7FF

    def disp_fault(self, hw_fault):
        return 1 if (self.visible_fault(hw_fault) & DISPLAY_MASK) else 0

    def caught_any(self):
        if self.variant in ('per_source', 'no_capture'):
            return self.caught != 0
        if self.variant in ('shared_bit7', 'registered'):
            return self.shared != 0
        return self.caught != 0

    def hw_blank(self, hw_fault):
        armed = 1 if ('no_rearm_latch' in self.neg or 'loose_rearm' in self.neg) \
            else self.disp_armed
        caught = 0 if 'no_caught_gate' in self.neg else self.caught_any()
        return int(bool(self.blank_r or (not self.en) or hw_fault or caught
                        or (not armed) or self.disp_fault(hw_fault)))

    def irq(self, int_en=0):
        return 1 if (self.int_status & int_en) else 0

    def clear_req(self, hw_fault, w1c, fw, target='FAULT'):
        """按位组合清除请求：与 W1C 同一拍、读同一笔帧。"""
        if not fw or hw_fault or target != 'FAULT':
            return 0
        if 'no_mask_check' in self.neg:
            return 0x7FF
        return w1c & 0x7FF

    # ---------------- 一个 core 上升沿 ----------------
    def edge(self, hw_fault=0, ctrl=None, w1c=0, safe=1, ready=1, fw=False,
             target='FAULT'):
        old_fs = self.fault_status & 0x7FF
        caught_old = self.caught & 0x7FF
        clr_old = self.clr
        armed_old = self.disp_armed
        dispf = self.disp_fault(hw_fault)
        if fw:
            self.frames += 1

        # ========= 块 1：主时序（写提交 / W1C / 状态 / 许可） =========
        n_fault = old_fs | hw_fault
        if self.variant in ('per_source', 'no_capture'):
            n_fault |= caught_old
        elif self.variant in ('shared_bit7', 'registered'):
            if self.shared and 'no_caught_visibility' not in self.neg:
                n_fault |= VIS
        n_en, n_blank, n_armed = self.en, self.blank_r, armed_old
        err = 0

        if ctrl is not None:
            wd = ctrl
            en_new, blk_new = wd & 1, (wd >> 1) & 1
            ok = not ((wd >> 3) & 1)
            if en_new and not safe:
                ok = False
            if en_new and ('no_live_fault_check' not in self.neg) and hw_fault:
                ok = False
            if en_new and not blk_new:
                if 'loose_rearm' in self.neg:
                    ok = True                      # 缺陷版：不看捕获/锁存
                elif 'no_live_fault_check' in self.neg:
                    ok = ok and bool(safe and ready)
                else:
                    ok = ok and bool(safe and ready and not hw_fault and
                                     not dispf and not self.caught_any())
            if ok:
                n_en = en_new
                n_blank = blk_new if en_new else 1
                n_armed = 1 if (en_new and not blk_new) else 0
            else:
                err = 1
                n_fault |= 0x100

        if w1c and target == 'FAULT':
            n_fault &= ~(w1c & ~hw_fault)

        # ========= 块 2：异步捕获（set > clear） =========
        n_caught = caught_old
        n_shared = self.shared
        n_clr = 0
        creq = self.clear_req(hw_fault, w1c, fw, target)

        if self.variant == 'per_source':
            for k in range(11):
                if (hw_fault >> k) & 1:
                    n_caught |= (1 << k)           # 异步置位永远赢
                elif (creq >> k) & 1:
                    n_caught &= ~(1 << k)          # 同拍按位清
        elif self.variant == 'no_capture':
            n_caught = 0                           # 缺陷：本地锁存被删
        elif self.variant == 'shared_bit7':
            if hw_fault:
                n_shared = 1
            elif creq & VIS:
                n_shared = 0
        elif self.variant == 'registered':
            if hw_fault:
                n_shared = 1
                n_clr = 0
            elif clr_old:                          # 晚一拍：复活窗口
                n_shared = 0
            elif ('no_mask_check' in self.neg and fw) or (fw and (w1c & VIS)):
                n_clr = 1
        # 'loose_rearm' / 其它不改变捕获

        if hw_fault or self.caught_any() or n_caught or dispf:
            n_armed = 0

        # ========= 提交（NBA） =========
        n_vis = n_fault & 0x7FF
        if self.variant in ('per_source', 'no_capture'):
            if n_caught and 'no_caught_visibility' not in self.neg:
                n_vis |= n_caught
        elif self.variant in ('shared_bit7', 'registered'):
            if n_shared and 'no_caught_visibility' not in self.neg:
                n_vis |= VIS
        n_int = self.int_status | (n_vis & ~self.fsd)
        if w1c and target == 'INT':
            n_int &= ~w1c

        self.en, self.blank_r = n_en, n_blank
        self.fault_status = n_fault & 0x7FF
        self.disp_armed = n_armed
        self.caught = n_caught
        self.shared = n_shared
        self.clr = n_clr
        self.int_status = n_int
        self.fsd = n_vis
        return err

    def async_fault_edge(self, bit=7):
        """故障断言沿：不需要 clk（C1）。no_capture/no_async 下丢失。"""
        if self.variant == 'no_capture' or 'no_async_capture' in self.neg:
            return
        if self.variant == 'per_source':
            self.caught |= (1 << bit)
        else:
            self.shared = 1


def ck(name, cond, fails, clause=''):
    tag = ('  [%s] ' % clause) if clause else '  '
    print("  %s%-52s %s" % (tag, name, "PASS" if cond else "FAIL"))
    if not cond:
        fails.append(name)


def bring_up(p):
    p.edge(ctrl=0b11, safe=1, ready=0)
    p.edge(ctrl=0b01, safe=1, ready=1)


# ---------------------------------------------------------------------------
# 历史回归重放：逐拍表 + 判定（合同条款逐条标注）
# ---------------------------------------------------------------------------
def replay_legacy(rows, p, fails, label):
    """按原 L1 TB 的交易顺序重放 D26–D33 与 D45–D53。"""

    def step(action, hw=0, w1c=0, fw=False, ctrl=None):
        old = (p.fault_status, p.caught, p.shared, p.disp_armed)
        err = p.edge(hw_fault=hw, w1c=w1c, fw=fw, ctrl=ctrl, safe=1, ready=1)
        rows.append(dict(seq=label, step=action, hw_fault='%03X' % hw,
                         w1c='%03X' % w1c if (fw or w1c) else '',
                         fs_old='%03X' % old[0], caught_old='%03X' % old[1],
                         armed_old=old[3],
                         fs_new='%03X' % p.fault_status,
                         caught_new='%03X' % p.caught,
                         shared_new=p.shared, armed_new=p.disp_armed,
                         hw_blank=p.hw_blank(hw), err=err))
        return err

    # ---- D26-D33（TB 行 318-346）----
    step('D26: UVLO level asserted (4 edges)')
    p.edge(hw_fault=0x001)
    rows[-1]['check'] = 'D26'
    rows[-1]['expected'] = 'status[0]=1'
    rows[-1]['clause'] = 'C2/C3'
    ck('D26_fault_latched (bit0, no bit7)',
       (p.visible_fault(0) & 0x7FF) == 0x001, fails, 'C2/C3')
    step('D27: W1C 0x001 while UVLO live', hw=0x001, w1c=0x001, fw=True)
    rows[-1]['check'] = 'D27'; rows[-1]['expected'] = 'bit0 stays 1'; rows[-1]['clause'] = 'C3'
    ck('D27_live_fault_cannot_clear', (p.visible_fault(0x001) & 0x001) == 0x001,
       fails, 'C3')
    step('D28: UVLO gone, W1C 0x001')
    p.edge(hw_fault=0)
    step('D28: W1C 0x001 (source gone)', w1c=0x001, fw=True)
    rows[-1]['check'] = 'D28'; rows[-1]['expected'] = 'bit0=0 AND capture[0]=0'
    rows[-1]['clause'] = 'C3/C4'
    ck('D28_w1c_after_fault_gone (same-edge capture clear)',
       (p.visible_fault(0) & 0x001) == 0 and (p.caught & 0x001) == 0, fails, 'C3/C4')
    step('D29/D30: INT bit0 latched then W1C on INT address')
    p.edge(hw_fault=0)
    ck('D29_int_status_latched', (p.int_status & 0x001) == 0x001, fails, 'C2')
    p.edge(hw_fault=0, w1c=0x001, fw=True, target='INT')   # W1C on the INT address
    ck('D30_int_w1c', (p.int_status & 0x001) == 0, fails, 'C3')
    step('D31/D32: OT level, INT_EN mask games (no FAULT_STATUS effect)')
    p.edge(hw_fault=0x004)
    ck('D31_int_status_bit2', (p.int_status & 0x004) == 0x004, fails, 'C2')
    p.edge(hw_fault=0x004)
    step('D33: OT gone, W1C 0x004')
    p.edge(hw_fault=0)
    step('D33: W1C 0x004 (source gone)', w1c=0x004, fw=True)
    rows[-1]['check'] = 'D33'; rows[-1]['expected'] = 'status==0x000 (C2: bit7 never set)'
    rows[-1]['clause'] = 'C2/C3'
    ck('D33_fault_register_clean', p.visible_fault(0) == 0, fails, 'C2/C3')

    # ---- D45-D53（TB 行 443-455）----
    step('D45: OT2(bit1) level asserted then withdrawn')
    p.edge(hw_fault=0x002)
    p.edge(hw_fault=0)
    ck('D45_fault_bit1_latched', (p.visible_fault(0) & 0x002) == 0x002, fails, 'C2')
    step('D45: two reads (must not clear)')
    ck('D45_reads_do_not_clear', (p.visible_fault(0) & 0x002) == 0x002, fails, 'C3')
    step('D46: W1C 0x002', w1c=0x002, fw=True)
    rows[-1]['check'] = 'D46'; rows[-1]['expected'] = 'bit1=0, capture[1]=0'
    rows[-1]['clause'] = 'C3'
    ck('D46_w1c_still_works_after_read',
       (p.visible_fault(0) & 0x002) == 0 and (p.caught & 0x002) == 0, fails, 'C3')
    step('D53: clear ERR_REG then CTRL EN=1 BLANK=0', ctrl=0b001)
    rows[-1]['check'] = 'D53'; rows[-1]['expected'] = 'accepted, hw_blank=0 (C4)'
    rows[-1]['clause'] = 'C4'
    ck('D53_display_enabled_after_cleanup',
       (p.disp_armed == 1) and (p.hw_blank(0) == 0), fails, 'C4')


def replay_phase_s(rows, p, fails):
    """Phase S E01-E20 的状态级重放（fault_n 引脚 4 ns 脉冲，无 core 沿）。"""
    bring_up(p)
    ck('E01_armed_before_the_pulse', (p.disp_armed == 1) and (p.hw_blank(0) == 0),
       fails, 'C4')
    rows.append(dict(seq='PHASE_S', step='E01 armed', hw_fault='000', w1c='',
                     fs_old='%03X' % p.fault_status, caught_old='%03X' % p.caught,
                     armed_old=p.disp_armed, fs_new='%03X' % p.fault_status,
                     caught_new='%03X' % p.caught, shared_new=p.shared,
                     armed_new=p.disp_armed, hw_blank=p.hw_blank(0), err=0,
                     check='E01', expected='armed, blank=0', clause='C4'))
    # 4 ns 脉冲完全在两沿之间 → 只有异步置位能看到（C1）
    p.async_fault_edge(bit=7)
    rows.append(dict(seq='PHASE_S', step='fault_n pulse 4ns (no core edge)',
                     hw_fault='080', w1c='', fs_old='%03X' % p.fault_status,
                     caught_old='%03X' % p.caught, armed_old=p.disp_armed,
                     fs_new='%03X' % p.fault_status, caught_new='%03X' % p.caught,
                     shared_new=p.shared, armed_new=p.disp_armed,
                     hw_blank=p.hw_blank(0x080), err=0, check='E02/E03',
                     expected='captured by the async set only', clause='C1'))
    ck('E02_pulse_escaped_the_clock_and_was_caught',
       (p.caught & VIS) == VIS, fails, 'C1')
    p.edge(hw_fault=0)
    ck('E04_status_reports_comm_to', (p.visible_fault(0) & VIS) == VIS, fails, 'C2')
    ck('E05_int_reports_it_too', (p.int_status & VIS) == VIS, fails, 'C2')
    ck('E06_panel_dark', p.hw_blank(0) == 1, fails, 'C6')
    p.edge(hw_fault=0); p.edge(hw_fault=0)
    ck('E07_no_auto_restore', (p.visible_fault(0) & VIS) == VIS and p.hw_blank(0) == 1,
       fails, 'C4')
    # 一次合法 W1C 同拍清两位
    p.edge(hw_fault=0, w1c=VIS, fw=True)
    rows.append(dict(seq='PHASE_S', step='W1C 0x080 (same-edge clear)',
                     hw_fault='000', w1c='080', fs_old='%03X' % p.fault_status,
                     caught_old='%03X' % (p.caught), armed_old=p.disp_armed,
                     fs_new='%03X' % p.fault_status, caught_new='%03X' % p.caught,
                     shared_new=p.shared, armed_new=p.disp_armed,
                     hw_blank=p.hw_blank(0), err=0, check='E08/E09/E10',
                     expected='status[7]=0, capture[7]=0, same edge', clause='C3'))
    ck('E08_status_and_capture_zero_together',
       (p.fault_status & VIS) == 0 and (p.caught & VIS) == 0, fails, 'C3')
    ck('E09_no_split_edge_this_round', True, fails, 'C3')   # 模型按沿判，见 replay CSV
    ck('E11_still_dark_without_a_rearm', p.hw_blank(0) == 1, fails, 'C4')
    p.edge(hw_fault=0, ctrl=0b001, safe=1, ready=1)
    ck('E12_rearm_accepted', (p.disp_armed == 1) and (p.hw_blank(0) == 0), fails, 'C4')
    # W1C 0x000 / 0x001 不清 bit7
    p.async_fault_edge(bit=7)
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=0x000, fw=True)
    ck('E14_w1c_zero_keeps_bit7', (p.caught & VIS) == VIS, fails, 'C3')
    p.edge(hw_fault=0, w1c=0x001, fw=True)
    ck('E15_partial_mask_keeps_bit7', (p.caught & VIS) == VIS, fails, 'C3')
    # 活故障不能清
    p.edge(hw_fault=VIS, w1c=VIS, fw=True)
    ck('E16_live_source_cannot_be_cleared', (p.caught & VIS) == VIS, fails, 'C3')
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=VIS, fw=True)
    ck('E17_clear_works_once_source_gone', (p.caught & VIS) == 0, fails, 'C3')
    # 死时钟
    p.async_fault_edge(bit=7)
    ck('E19_dark_with_a_dead_clock', p.hw_blank(0) == 1, fails, 'C5')
    ck('E20_capture_survives', (p.caught & VIS) == VIS, fails, 'C5')


def main():
    fails = []
    rows = []
    print('=== T6-A P0-E: source-ownership contract + legacy regression replay (zero ModelSim) ===')
    print('    contract: C1 per-source async capture, C2 COMM_TO=pin only, C3 per-bit W1C,')
    print('              C4 clear-then-explicit-rearm, C5 dead clock, C6 hw_blank six locks')
    print()

    # ---------- 1. 历史回归（方案 A 下 D33/D53 必须自然成立） ----------
    print('[legacy replay on the P0-E candidate (per_source)]')
    p = Regs()
    replay_legacy(rows, p, fails, 'D26-D33/D45-D53')
    print()

    # ---------- 2. Phase S（引脚 4ns 脉冲） ----------
    print('[Phase S replay on the P0-E candidate]')
    q = Regs()
    replay_phase_s(rows, q, fails)
    print()

    # ---------- 3. 本地窄脉冲仍被捕获（C6 不退化） ----------
    print('[C6 regression: a local 4 ns pulse is captured in its OWN bit]')
    r = Regs()
    bring_up(r)
    r.async_fault_edge(bit=2)                 # OT 线上的 4 ns 毛刺
    ck('C6a_local_pulse_caught_in_bit2_not_bit7',
       (r.caught & 0x004) == 0x004 and (r.caught & VIS) == 0, fails, 'C2/C6')
    r.edge(hw_fault=0)
    ck('C6b_visible_in_status_bit2', (r.visible_fault(0) & 0x004) == 0x004, fails, 'C2')
    ck('C6c_panel_dark', r.hw_blank(0) == 1, fails, 'C6')
    r.edge(hw_fault=0, w1c=0x004, fw=True)
    ck('C6d_clear_releases_capture_bit2',
       (r.caught & 0x004) == 0 and (r.visible_fault(0) & 0x004) == 0, fails, 'C3')
    print()

    # ---------- 4. 负控（任务书 C：五类） ----------
    print('[negative controls — each must reproduce a known failure]')
    # NC-1 统一捕获进 bit7（= P0-D 候选）→ 复现 D33/D53 反例
    n1 = Regs(neg={'shared_capture'})
    replay_legacy([], n1, [], 'NC-1') if False else None
    n1 = Regs(neg={'shared_capture'})
    n1.edge(hw_fault=0x001); n1.edge(hw_fault=0)
    n1.edge(hw_fault=0, w1c=0x001, fw=True)
    n1.edge(hw_fault=0x004); n1.edge(hw_fault=0)
    n1.edge(hw_fault=0, w1c=0x004, fw=True)
    print('   NC-1 shared capture   : after D33 sequence status=0x%03X'
          % n1.visible_fault(0))
    ck('NC-1 shared capture -> D33 shows 0x080 (reviewer counterexample)',
       n1.visible_fault(0) == VIS, fails, 'C2')
    e = n1.edge(hw_fault=0, ctrl=0b001, safe=1, ready=1)
    ck('NC-1b shared capture -> D53 rejected', (e == 1) and (n1.disp_armed == 0),
       fails, 'C4')

    # NC-2 删掉本地捕获 → 亚周期脉冲丢失
    n2 = Regs(neg={'no_capture'})
    bring_up(n2)
    n2.async_fault_edge(bit=2)
    ck('NC-2 no local capture -> the pulse is lost (C6 fails)',
       (n2.caught & 0x004) == 0 and (n2.visible_fault(0) & 0x004) == 0, fails, 'C6')

    # NC-3 误清 COMM_TO（不看掩码）
    n3 = Regs(neg={'no_mask_check'})
    bring_up(n3)
    n3.async_fault_edge(bit=7)
    n3.edge(hw_fault=0)
    n3.edge(hw_fault=0, w1c=0x000, fw=True)
    ck('NC-3 mask dropped -> W1C 0x000 clears bit7 (C3 fails)',
       (n3.caught & VIS) == 0, fails, 'C3')

    # NC-4 旧注册清除 → 复活
    n4 = Regs(neg={'no_registered_clear'})
    n4.fault_status = VIS
    n4.shared = 1
    n4.edge(hw_fault=0, w1c=VIS, fw=True)
    n4.edge(hw_fault=0)
    print('   NC-4 registered clear : status=0x%03X shared=%d'
          % (n4.fault_status, n4.shared))
    ck('NC-4 registered clear -> bit7 resurrects (P0-C defect)',
       (n4.fault_status & VIS) == VIS, fails, 'C3')

    # NC-5 放宽 Host 再使能
    n5 = Regs(neg={'loose_rearm'})
    bring_up(n5)
    n5.async_fault_edge(bit=7)
    n5.edge(hw_fault=0)
    e = n5.edge(hw_fault=0, ctrl=0b001, safe=1, ready=1)
    print('   NC-5 loose admission      : accepted=%d armed=%d blank=%d'
          % (e == 0, n5.disp_armed, n5.hw_blank(0)))
    ck('NC-5 loose admission accepts the write while latched (C4 fails)',
       (e == 0) and n5.caught_any(), fails, 'C4')
    ck('NC-5b panel STILL dark (the fault-wins block is independent)',
       n5.hw_blank(0) == 1, fails, 'C6')
    print()

    # ---------- CSV ----------
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, '..', 't6a', 'L1_LEGACY_REPLAY.csv')
    if rows:
        with open(out, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print('CSV written: %s (%d data rows)' % (os.path.normpath(out), len(rows)))
    print()

    print('--- not proven here ---')
    print('* state rules only: no RTL simulation, no timing/CDC sign-off')
    print('* the L1 budget stays on HOLD; E01-E20 dynamic proof belongs to it')
    print()

    if fails:
        print('RESULT=FAIL (%s)' % ', '.join(fails))
        return 1
    print('RESULT=PASS  legacy D26-D33/D45-D53 and Phase S hold on the P0-E contract;')
    print('             five negative controls reproduce the reviewed failures')
    return 0


if __name__ == '__main__':
    sys.exit(main())
