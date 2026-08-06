/* =============================================================================
 * 智慧香爐 — 零件：插孔板（理香機構）
 * =============================================================================
 * 理香機構的一部分（用途見 ../params.scad 的「理香機構」段）。
 * 尺寸全部來自 ../params.scad，本檔不寫死任何數字。
 * ★這套機構不需要明火★——插未點燃的香就能演示。
 * ============================================================================= */

include <../common.scad>


// 原點：板底面圓心。孔位在 (±pitch/2, ±pitch/2)。
module tidy_holes(d, h, z = -0.1) {
    o = TIDY_HOLE_PITCH / 2;
    for (x = [-o, o], y = [-o, o])
        translate([x, y, z]) cylinder(h = h, d = d);
}

module socket_plate() {
    difference() {
        // 不做外凸法蘭——板子要能從罩頂開口放進去，多一圈凸緣只會卡住。
        // 改由集煙罩內側的四個凸耳承接（見 parts/hood.scad）。
        cylinder(h = TIDY_PLATE_T, d = TIDY_PLATE_DIA);
        // 套筒孔——★要留餘隙讓套筒能擺動，才回正得了★
        tidy_holes(TIDY_HOLE_DIA, TIDY_PLATE_T + 0.2);

        // M4 通孔（鎖到磁座的螺柱上）
        for (a = [0, 90, 180, 270])   // 與磁座螺柱同角度（見 magnet_deck.scad）
            translate([TIDY_BOLT_R * cos(a), TIDY_BOLT_R * sin(a), -0.1])
                cylinder(h = TIDY_PLATE_T + 0.2, d = M4_CLEAR);
    }
}

// ── 單獨開檔時的預覽（被 use<> 引入時不執行）──
socket_plate();
