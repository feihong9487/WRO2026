/* =============================================================================
 * 智慧香爐 — 零件：電磁鐵座（理香機構）
 * =============================================================================
 * 理香機構的一部分（用途見 ../params.scad 的「理香機構」段）。
 * 尺寸全部來自 ../params.scad，本檔不寫死任何數字。
 * ★這套機構不需要明火★——插未點燃的香就能演示。
 * ============================================================================= */

include <../common.scad>


// 原點：磁座頂面圓心，往下長。電磁鐵由★上方★放進凹槽，再把插孔板鎖上壓住。
module magnet_deck() {
    pocket_d = TIDY_MAGNET_DIA + FIT * 2;
    total_h  = TIDY_MAGNET_H + TIDY_DECK_FLOOR;
    o = TIDY_HOLE_PITCH / 2;

    difference() {
        union() {
            translate([0, 0, -total_h])
                cylinder(h = total_h, d = TIDY_DECK_DIA);
            // M4 自攻螺柱（撐住插孔板，高度＝鐵墊圈厚＋磁隙）
            // ★往下埋 1mm★ 只讓底面與磁座頂面共平面的話，CGAL 不保證併成
            //   一體，會變成浮空的獨立實體（實測 Volumes 6）——
            //   跟感測器艙凸耳踩過的是同一個坑。
            // ★螺柱角度必須避開磁鐵凹槽★ 原本兩者都放 45°，
            //   螺柱整根落在凹槽孔內：下半截被挖掉、上半截浮空
            //   （實測 Volumes 2 → 6）。改放 0/90/180/270 錯開。
            for (a = [0, 90, 180, 270])
                translate([TIDY_BOLT_R * cos(a), TIDY_BOLT_R * sin(a), -1])
                    standoff(h = TIDY_STANDOFF_H + 1, pilot = M4_PILOT);
        }
        // 電磁鐵凹槽（頂面開口，方便放入）
        for (x = [-o, o], y = [-o, o])
            translate([x, y, -TIDY_MAGNET_H])
                cylinder(h = TIDY_MAGNET_H + 0.1, d = pocket_d);
        // 線圈出線孔：每個凹槽底部穿一個孔，引線往下走
        // ★不要在側面開放射狀長槽★——四道槽會在中央互相交會，
        //   把磁座切成 5 塊（實測 Volumes 從 2 變 6）。
        for (x = [-o, o], y = [-o, o])
            translate([x, y, -TIDY_MAGNET_H - TIDY_DECK_FLOOR - 0.1])
                cylinder(h = TIDY_DECK_FLOOR + 0.2, d = 5);
    }
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
magnet_deck();
