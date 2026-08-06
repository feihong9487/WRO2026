/* =============================================================================
 * 智慧香爐 — 零件：感測器艙
 * =============================================================================
 * 尺寸全部來自 ../params.scad，本檔不寫死任何數字。
 *
 * 單獨開這個檔（F5／F6）會直接看到這個零件；被 incense_burner.scad 以
 * ★use<>★ 引入時，檔尾的預覽呼叫不會執行——use 只帶進模組、不執行對方的
 * 頂層敘述，這正是「一檔一零件」又不污染組合件的作法。
 * ============================================================================= */

include <../common.scad>

// ═══════════════════════════════════════════════════════════════════════════
// 零件 5：感測器艙
// ═══════════════════════════════════════════════════════════════════════════
// 位置在前方下緣，遠離熱源，開口朝向參拜者呼吸帶——
// 這符合 FSM 用 CO2 斜率偵測人潮的設計意圖：量的是「人呼吸到的空氣」。
// ★2026-08-02 重寫★ 原本掛耳與模組卡槽都寫在 difference() 的 union() 裡，
//   但內部挖空 rrect(..., POD_D - WALL, ...) 從 y=WALL 一路開到 y=POD_D
//   （背面全開），把落在那個範圍內的掛耳與卡槽★整個吃掉★——
//   算出來的仍是合法實體，Volumes=2、watertight、參數檢查全過，
//   但功能特徵根本不存在：艙體鎖不上底座，感測器也沒東西夾。
//   （是把零件單獨算繪出來看背面才發現的，數值檢查一項都沒響。）
//   修法：挖空只作用在「殼」上，掛耳與定位肋在挖空之後才 union 進來。
module pod_ear() {
    difference() {
        cube([POD_EAR_W, POD_EAR_T, POD_EAR_H]);
        for (dx = [-1, 1])
            translate([POD_EAR_W / 2 + dx * POD_EAR_PITCH / 2, -0.1, POD_EAR_H / 2])
                rotate([-90, 0, 0])
                    cylinder(h = POD_EAR_T + 0.2, d = M4_CLEAR);
    }
}

// 模組定位肋：兩側各一道，夾住 PCB 的左右邊緣。
// ★不做成封閉滑槽★ 兩個理由：
//   1) 艙內高度不夠讓 PCB 從上往下滑進槽裡（上方只剩 8mm，板高 14mm）
//   2) 不需要——背面開放，PCB 由背面推入貼著前壁；
//      感測器艙鎖上底座後，底座前壁就是後擋板，把 PCB 壓住
// 肋條一路從艙底（FLOOR）長上來，不從半空開始，否則第一層無支撐。
module pod_rails(pcb_w, y0, depth, z0, z_len) {
    span = pcb_w + FIT * 2;
    top  = z0 + z_len;
    for (dx = [-1, 1]) {
        A  = POD_W / 2 + dx * (span / 2);        // PCB 的左／右邊緣
        rx = dx > 0 ? A : A - POD_RIB_W;         // 肋條一律長在 PCB 外側
        // 上擋／下擋：★只在肋條上做往內伸 2mm 的小凸耳，不做橫跨整寬的擋片★
        //   橫跨整寬的擋片會壓在前壁的通風槽上——驗證 L 抓到的就是這個：
        //   兩道擋片共擋掉 115mm³，等於把中間三道槽各截去 2mm 高度。
        //   凸耳只佔 PCB 兩側角落，通風槽的視線完全不受影響。
        // ★凸耳必須埋進肋條 1mm★ 只靠邊對邊接觸會產生非流形邊
        //   （Simple=no，切片器直接拒收）——這也踩過一次。
        tx = dx > 0 ? A - 2 : A - 1;
        translate([rx, y0, FLOOR])
            cube([POD_RIB_W, depth, top + 2 - FLOOR]);
        translate([tx, y0, top]) cube([3, depth, 2]);
        if (z0 > FLOOR + 0.01)       // z0 就在艙底時，艙底本身就是落座面
            translate([tx, y0, z0 - 2]) cube([3, depth, 2]);
    }
}

module sensor_pod() {
    union() {
        difference() {
            rrect_chamfered(POD_W, POD_D, POD_H, 5);

            // 內部挖空（背面開放，方便置入模組與走線）
            // 背面加 OVER，不讓切面停在與外殼共平面的位置（見檔頭 OVER 說明）。
            translate([WALL, WALL, FLOOR])
                rrect(POD_W - WALL * 2, POD_D - WALL + OVER, POD_H - FLOOR * 2,
                      5 - WALL);

            // 前面通風柵格——感測器必須接觸到外界空氣才量得準。
            // ★x 位置必須避開背面的定位肋★ 肋條貼在前壁內面，
            //   壓在槽上就等於把槽封死：外面看得到孔，裡面其實不通氣。
            //   （原本 5 槽等距 pitch=8，正好被兩對肋壓住兩槽）
            for (vx = POD_VENT_X)
                translate([vx, -0.5, POD_H / 2]) rotate([-90, 0, 0])
                    vent_slots(1, 3.5, 26, 0, WALL + 1);
        }

        // 背面掛耳（M4 鎖到底座前壁的螺柱上）——★必須在挖空之後★
        // 用外輪廓 intersection 修邊，橫樑才不會從圓角處凸出去。
        intersection() {
            translate([POD_EAR_X, POD_D - POD_EAR_T, POD_EAR_Z]) pod_ear();
            rrect(POD_W, POD_D, POD_H, 5);
        }

        // 模組定位肋（下 SCD41、上 SHT31）——★同樣必須在挖空之後★
        pod_rails(SCD41_W, POD_Y_SCD, POD_RIB_D_SCD, FLOOR, SCD41_D + FIT * 2);
        pod_rails(SHT31_W, POD_Y_SHT, POD_RIB_D_SHT,
                  FLOOR + SCD41_D + FIT * 2 + 8, SHT31_D + FIT * 2);
    }
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
sensor_pod();
