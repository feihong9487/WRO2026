// public.js — 公開展示頁：免登入，只讀
import { connect } from "./live.js";
import { createBoard } from "./board.js";

createBoard({ isPublic: true });
connect("/api/public/stream");
