import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AppLanguage = "en" | "vi";

interface LanguageContextValue {
  language: AppLanguage;
  setLanguage: (language: AppLanguage) => void;
  t: (text: string) => string;
}

const STORAGE_KEY = "chesscv.language";

const VI_TRANSLATIONS: Record<string, string> = {

  "Home": "Trang chủ",
  "Position": "Vị trí",
  "Live": "Trực tiếp",
  "Games": "Ván cờ",
  "Import PGN": "Nhập PGN",
  "Calibration": "Hiệu chỉnh",

  "Main navigation": "Điều hướng chính",
  "Pages": "Các trang",

  "Expand sidebar": "Mở rộng thanh bên",
  "Collapse sidebar": "Thu gọn thanh bên",
  "Expand menu": "Mở rộng menu",
  "Collapse menu": "Thu gọn menu",

  "Language": "Ngôn ngữ",
  "Switch to English": "Chuyển sang tiếng Anh",
  "Switch to Vietnamese": "Chuyển sang tiếng Việt",
  "English": "Tiếng Anh",
  "Vietnamese": "Tiếng Việt",

  // HOME

  "Physical chessboard recognition and game analysis system.":
    "Hệ thống nhận diện bàn cờ vật lý và phân tích ván cờ.",

  // UPLOAD POSITION

  "Upload Position": "Tải vị trí",

  "Choose an image from your computer or capture a frame directly from the physical chess camera.":
    "Chọn ảnh từ máy tính hoặc chụp trực tiếp một khung hình từ camera bàn cờ.",

  "or": "hoặc",
  "Open Camera": "Mở camera",
  "Close Camera": "Đóng camera",
  "Live chess camera": "Camera cờ vua trực tiếp",

  "Capturing...": "Đang chụp...",
  "Capture Photo": "Chụp ảnh",
  "Recognizing...": "Đang nhận diện...",
  "Recognize Position": "Nhận diện vị trí",

  "Side to move": "Lượt đi của",
  "White": "Trắng",
  "Black": "Đen",

  "Scan another image": "Quét ảnh khác",
  "Recognized board FEN": "FEN bàn cờ đã nhận diện",

  "Could not capture camera frame.":
    "Không thể chụp khung hình từ camera.",

  "Please select or capture an image first.":
    "Vui lòng chọn hoặc chụp ảnh trước.",

  "Please select exactly 8 calibration points.":
    "Vui lòng chọn chính xác 8 điểm hiệu chỉnh.",

  "Unknown recognition error.":
    "Lỗi nhận diện không xác định.",

  // FIXED CALIBRATION

  "Fixed Board Calibration": "Hiệu chỉnh bàn cờ cố định",

  "Set the four corners of the physical chessboard from the camera.":
    "Đánh dấu bốn góc của bàn cờ vật lý từ camera.",

  "Frozen frame": "Khung hình đã đóng băng",
  "Live camera": "Camera trực tiếp",

  "Press Freeze frame to select corners":
    "Nhấn Đóng băng khung hình để chọn các góc",

  "Capture again": "Chụp lại",
  "Freeze frame": "Đóng băng khung hình",
  "Resume live": "Tiếp tục camera trực tiếp",

  "Frozen camera for calibration":
    "Khung hình camera đã đóng băng để hiệu chỉnh",

  "Live camera preview": "Xem trước camera trực tiếp",

  "Select chessboard corner on frozen frame":
    "Chọn góc bàn cờ trên khung hình đã đóng băng",

  "Click the four outer corners of the 8×8 PLAYING AREA, not the wooden border.":
    "Nhấp vào bốn góc ngoài của VÙNG CHƠI 8×8, không phải viền gỗ.",

  "The preview is live. Freeze a frame before selecting points.":
    "Hình xem trước đang trực tiếp. Hãy đóng băng một khung hình trước khi chọn điểm.",

  "Board corners": "Các góc bàn cờ",

  "Click in this exact order, as in src/calibration.py:":
    "Nhấp theo đúng thứ tự này, như trong src/calibration.py:",

  "Not selected": "Chưa chọn",
  "Undo last point": "Hoàn tác điểm cuối",
  "Reset points": "Đặt lại các điểm",

  "Saving...": "Đang lưu...",
  "Save Fixed Board": "Lưu hiệu chỉnh bàn cờ",

  "Stop Live Game before saving.":
    "Hãy dừng ván trực tiếp trước khi lưu.",

  "The new configuration replaces":
    "Cấu hình mới sẽ thay thế",

  ". The previous version is backed up as":
    ". Phiên bản trước được sao lưu thành",

  "Could not read camera image.":
    "Không thể đọc ảnh camera.",

  "Could not save calibration.":
    "Không thể lưu hiệu chỉnh.",

  "Future Live Games will use the new position.":
    "Các ván trực tiếp tiếp theo sẽ sử dụng vị trí mới.",

  "Fixed board calibration saved to config/calibration.json. Future Live Games will use the new position.":
    "Đã lưu hiệu chỉnh bàn cờ vào config/calibration.json. Các ván trực tiếp tiếp theo sẽ sử dụng vị trí mới.",

  // GAMES HISTORY

  "Games History": "Lịch sử ván cờ",

  "Games saved in MySQL. Opening recognition is performed when a game is saved. Select a game to replay its moves and review it with Stockfish.":
    "Các ván cờ được lưu trong MySQL. Hệ thống nhận diện khai cuộc khi lưu ván. Chọn một ván để phát lại nước đi và phân tích bằng Stockfish.",

  "Loading games...": "Đang tải danh sách ván cờ...",
  "Loading...": "Đang tải...",

  "No saved games yet.":
    "Chưa có ván cờ nào được lưu.",

  "Finish a Live Game and press End & Save.":
    "Hoàn thành một ván trực tiếp và nhấn Kết thúc & Lưu.",

  "Date": "Ngày",
  "Result": "Kết quả",
  "Opening": "Khai cuộc",
  "Moves": "Nước đi",
  "Review": "Phân tích",

  "Replay / Analyze": "Phát lại / Phân tích",
  "Refresh": "Làm mới",

  "Could not load games.":
    "Không thể tải danh sách ván cờ.",

  // GAME REVIEW

  "Evaluation graph": "Biểu đồ đánh giá",
  "Click to jump to a move": "Nhấp để chuyển đến nước đi",

  "Clickable Stockfish evaluation graph":
    "Biểu đồ đánh giá Stockfish có thể tương tác",

  "Starting position": "Vị trí ban đầu",
  "Final position": "Vị trí cuối",

  "Loading saved game...": "Đang tải ván cờ đã lưu...",

  "← Games": "← Danh sách ván",
  "← All saved games": "← Tất cả ván đã lưu",

  "Game Review": "Phân tích ván cờ",

  "Evaluating moves and classifying game decisions. Longer games take more time.":
    "Đang đánh giá các nước đi và phân loại quyết định trong ván cờ. Ván càng dài sẽ cần nhiều thời gian hơn.",

  "Analyzing with Stockfish...":
    "Đang phân tích bằng Stockfish...",

  "Re-analyze game": "Phân tích lại ván cờ",
  "Analyze with Stockfish": "Phân tích bằng Stockfish",

  "Game board and players": "Bàn cờ và người chơi",
  "Flip board": "Lật bàn cờ",
  "Game result": "Kết quả ván cờ",

  "No saved board position available.":
    "Không có vị trí bàn cờ đã lưu.",

  "Stockfish suggestion · position before the selected move":
    "Gợi ý của Stockfish · vị trí trước nước đi được chọn",

  "Start of the game": "Bắt đầu ván cờ",

  "Select a move to see its classification, evaluation and the engine's best alternative.":
    "Chọn một nước đi để xem phân loại, đánh giá và phương án tốt nhất của engine.",

  "Ready to review this game?":
    "Sẵn sàng phân tích ván cờ này?",

  "Replay the saved moves, then select Analyze with Stockfish to see move-quality symbols and explanations.":
    "Phát lại các nước đã lưu, sau đó chọn Phân tích bằng Stockfish để xem ký hiệu chất lượng nước đi và giải thích.",

  "Played by": "Người đi",
  "Estimated accuracy": "Độ chính xác ước tính",

  "This is already the engine's first choice, or analysis is not available.":
    "Đây đã là lựa chọn đầu tiên của engine hoặc chưa có phân tích.",

  "Best move": "Nước đi tốt nhất",
  "Next": "Tiếp",

  "Showing the position before the played move, with Stockfish's proposed move marked by the blue arrow.":
    "Hiển thị vị trí trước nước đi đã thực hiện, với nước đề xuất của Stockfish được đánh dấu bằng mũi tên xanh.",

  "half-moves": "nửa nước",
  "No moves were saved.": "Không có nước đi nào được lưu.",

  "Game replay controls": "Điều khiển phát lại ván cờ",

  "First position": "Vị trí đầu tiên",
  "Previous move": "Nước trước",
  "Pause replay": "Tạm dừng phát lại",
  "Play moves automatically": "Tự động phát nước đi",
  "Pause": "Tạm dừng",
  "Auto replay": "Tự động phát lại",
  "Next move": "Nước tiếp theo",
  "Last position": "Vị trí cuối",
  "Start position": "Vị trí bắt đầu",

  "Estimated game accuracy":
    "Độ chính xác ước tính của ván",

  "Move quality": "Chất lượng nước đi",

  "Accuracy and all labels are estimates, not Chess.com scoring.":
    "Độ chính xác và các nhãn đều là ước tính, không phải điểm đánh giá của Chess.com.",

  "Saved PGN": "PGN đã lưu",
  "No PGN stored.": "Không có PGN được lưu.",

  "Invalid game ID.": "ID ván cờ không hợp lệ.",
  "Could not load game.": "Không thể tải ván cờ.",
  "Could not analyze game.": "Không thể phân tích ván cờ.",

  // MOVE CLASSIFICATIONS

  "Brilliant": "Xuất sắc đặc biệt",
  "Great": "Rất tốt",
  "Best": "Tốt nhất",
  "Excellent": "Xuất sắc",
  "Good": "Tốt",
  "Book": "Theo sách khai cuộc",
  "Inaccuracy": "Chưa chính xác",
  "Mistake": "Sai lầm",
  "Miss": "Bỏ lỡ",
  "Blunder": "Sai lầm nghiêm trọng",

  // IMPORT PGN

  "Add one chess game to your Games library. ChessCV validates every move, filters PGN headers and prepares the game for Replay / Analyze.":
    "Thêm một ván cờ vào thư viện ván đấu. ChessCV kiểm tra từng nước đi, lọc các header PGN và chuẩn bị dữ liệu cho chức năng Phát lại / Phân tích.",

  "View Games": "Xem ván cờ",
  "One game PGN": "Một ván PGN",

  "Paste a PGN or select a file from your computer.":
    "Dán PGN hoặc chọn tệp từ máy tính.",

  "Choose .pgn file": "Chọn tệp .pgn",
  "Choose a PGN file": "Chọn tệp PGN",

  "PGN content": "Nội dung PGN",
  "characters": "ký tự",

  "One PGN per import · mainline moves only":
    "Mỗi lần nhập một PGN · chỉ các nước chính",

  "Clear": "Xóa",
  "Load sample PGN": "Tải PGN mẫu",

  "Automatic header filtering":
    "Tự động lọc header",

  "The stored PGN keeps Event, Date, Round, White, Black and Result. For custom starting positions it also keeps SetUp and FEN.":
    "PGN được lưu giữ lại Event, Date, Round, White, Black và Result. Với vị trí bắt đầu tùy chỉnh, PGN cũng giữ SetUp và FEN.",

  "ECO and Opening are saved into the Games database columns. Extra tags such as Site, WhiteElo, BlackElo, TimeControl and Annotator are omitted from the stored PGN.":
    "ECO và Opening được lưu vào các cột tương ứng trong cơ sở dữ liệu Games. Các thẻ bổ sung như Site, WhiteElo, BlackElo, TimeControl và Annotator sẽ bị loại khỏi PGN đã lưu.",

  "ChessCV also generates SAN, UCI and the before/after FEN for every move, making replay possible without the original file.":
    "ChessCV cũng tạo SAN, UCI và FEN trước/sau cho từng nước đi, cho phép phát lại mà không cần tệp gốc.",

  "Validated game": "Ván cờ đã được kiểm tra",
  "Valid PGN": "PGN hợp lệ",
  "vs": "đấu với",

  "Half-moves": "Nửa nước",
  "Move number": "Số nước",
  "ECO": "ECO",

  "Replay will work. Current Stockfish Game Review is limited to 400 half-moves.":
    "Chức năng phát lại vẫn hoạt động. Phân tích ván cờ bằng Stockfish hiện giới hạn ở 400 nửa nước.",

  "Kept in PGN": "Được giữ trong PGN",
  "Saved in database fields": "Được lưu vào các trường cơ sở dữ liệu",

  "No ECO / Opening supplied or recognized":
    "Không có ECO / Khai cuộc được cung cấp hoặc nhận diện",

  "Excluded headers": "Các header bị loại",
  "No extra headers.": "Không có header bổ sung.",
  "Show cleaned PGN": "Hiển thị PGN đã làm sạch",

  "Game already in library": "Ván cờ đã có trong thư viện",
  "PGN imported successfully": "Nhập PGN thành công",

  "An identical game was found. No duplicate was created.":
    "Đã tìm thấy một ván cờ giống hệt. Không tạo bản trùng lặp.",

  "The game and all its moves are now saved in ChessCV MySQL.":
    "Ván cờ và toàn bộ nước đi đã được lưu vào MySQL của ChessCV.",

  "Validating...": "Đang kiểm tra...",
  "Preview PGN": "Xem trước PGN",
  "Importing...": "Đang nhập...",
  "Import to Games": "Nhập vào danh sách ván",

  "This PGN file is too large (maximum 250,000 characters).":
    "Tệp PGN quá lớn (tối đa 250.000 ký tự).",

  "This PGN contains more than 250,000 characters.":
    "PGN này chứa hơn 250.000 ký tự.",

  "Could not read the selected PGN file.":
    "Không thể đọc tệp PGN đã chọn.",

  "Paste one game PGN or select a .pgn file first.":
    "Hãy dán PGN của một ván cờ hoặc chọn tệp .pgn trước.",

  "Could not preview PGN.": "Không thể xem trước PGN.",
  "Could not import PGN.": "Không thể nhập PGN.",

  // PLAYER STATISTICS

  "Player Statistics": "Thống kê người chơi",

  "Player statistics will appear here.":
    "Thống kê người chơi sẽ xuất hiện tại đây.",

  // LIVE GAME

  "Live Game": "Ván cờ trực tiếp",

  "Track a physical game, play Human vs Human or against a chess bot, then save the result to MySQL.":
    "Theo dõi ván cờ trên bàn thật, chơi Người với Người hoặc đấu với bot, sau đó lưu kết quả vào MySQL.",

  "Result: *": "Kết quả: *",
  "Result: 1-0": "Kết quả: 1-0",
  "Result: 0-1": "Kết quả: 0-1",
  "Result: 1/2-1/2": "Kết quả: 1/2-1/2",

  "Stop": "Dừng",
  "End & Save": "Kết thúc & Lưu",

  "Board preview only. The physical camera remains the source of moves.":
    "Chỉ là bản xem trước bàn cờ. Camera bàn cờ vật lý vẫn là nguồn ghi nhận nước đi.",

  "Game Setup": "Thiết lập ván cờ",

  "Configure the game before starting the physical-board tracker.":
    "Cấu hình ván cờ trước khi khởi động bộ theo dõi bàn cờ vật lý.",

  "Game mode": "Chế độ chơi",
  "Human vs Human": "Người với Người",
  "Human vs Bot": "Người với Bot",

  "Choose your opponent": "Chọn đối thủ",
  "3 bots": "3 bot",
  "SOON": "SẮP CÓ",

  "Your side": "Quân của bạn",
  "Camera orientation": "Hướng camera",

  "White left / Black right": "Trắng bên trái / Đen bên phải",
  "Black left / White right": "Đen bên trái / Trắng bên phải",

  "Initial position": "Vị trí ban đầu",

  "Standard starting position":
    "Vị trí khai cuộc tiêu chuẩn",

  "Start the digital board from the normal chess starting position.":
    "Bắt đầu bàn cờ số từ vị trí khai cuộc tiêu chuẩn.",

  "Detect current position": "Nhận diện vị trí hiện tại",

  "Recognize the position currently visible on the physical board.":
    "Nhận diện vị trí hiện đang hiển thị trên bàn cờ vật lý.",

  "Start Game": "Bắt đầu ván",
  "Starting...": "Đang khởi động...",
  "VS": "ĐẤU",

  "Physical board": "Bàn cờ vật lý",
  "Physical chessboard": "Bàn cờ vật lý",

  "Green grid = detected 8×8 board area.":
    "Lưới xanh = vùng bàn cờ 8×8 được nhận diện.",

  "Keep all physical squares inside the grid.":
    "Giữ toàn bộ ô cờ vật lý nằm bên trong lưới.",

  "Move the bot's piece on the physical board according to this move. The system will verify it before continuing.":
    "Hãy di chuyển quân của bot trên bàn cờ vật lý theo nước đi này. Hệ thống sẽ xác minh trước khi tiếp tục.",

  "Digital board": "Bàn cờ số",
  "Waiting for position": "Đang chờ vị trí",

  "Turn:": "Lượt:",
  "Last move:": "Nước đi cuối:",

  "No moves yet.": "Chưa có nước đi.",

  "Opening recognition runs after the game is saved.":
    "Nhận diện khai cuộc sẽ chạy sau khi ván cờ được lưu.",

  "Current FEN": "FEN hiện tại",

  "Chessboard preview": "Xem trước bàn cờ",
  "Choose your bot opponent": "Chọn đối thủ bot",

  // BOT NAMES

  "Beginner Bot": "Bot cơ bản",
  "For relaxed games and new players":
    "Dành cho ván cờ thoải mái và người chơi mới",

  "Stockfish Bot": "Bot Stockfish",
  "A stronger tactical opponent":
    "Đối thủ chiến thuật mạnh hơn",

  "Grandmaster Bot": "Bot cấp đại kiện tướng",

  "Strong Stockfish opponent (approximately 2800 Elo)":
    "Đối thủ Stockfish mạnh (xấp xỉ 2800 Elo)",

  "Grandmaster Bot ~2800": "Bot Đại kiện tướng ~2800",
  "Stockfish Bot ~1800": "Bot Stockfish ~1800",
  "Beginner Bot ~800": "Bot cơ bản ~800",

  // COMMON STATUS

  "Live game is stopped.":
    "Ván cờ trực tiếp đã dừng.",

  "Board is partially covered. Digital state remains frozen.":
    "Bàn cờ đang bị che một phần. Trạng thái bàn cờ số được giữ nguyên.",

  "Observed position changed, but it is not yet a clear legal move.":
    "Vị trí quan sát được đã thay đổi, nhưng chưa xác định được một nước đi hợp lệ rõ ràng.",

  "Current board is visible, but recognition is not yet a valid chess position.":
    "Bàn cờ hiện đang hiển thị, nhưng vị trí nhận diện chưa phải một thế cờ hợp lệ.",

  "Fixed calibration loaded. Reading current physical position...":
    "Đã tải hiệu chỉnh cố định. Đang đọc vị trí bàn cờ vật lý...",

  "Live processing error. Digital board is frozen.":
    "Lỗi xử lý trực tiếp. Bàn cờ số được giữ nguyên.",

  "Game over.": "Ván cờ đã kết thúc.",

  "Start a game to load the board.":
    "Bắt đầu một ván cờ để tải bàn cờ.",

  "Current physical position loaded.":
    "Đã tải vị trí bàn cờ vật lý hiện tại.",

  "Could not prepare the first bot move.":
    "Không thể chuẩn bị nước đi đầu tiên của bot.",

  "Current physical position loaded. Waiting for White.":
    "Đã tải vị trí bàn cờ vật lý. Đang chờ Trắng.",

  "Current physical position loaded. Waiting for Black.":
    "Đã tải vị trí bàn cờ vật lý. Đang chờ Đen.",

  "Board stable. Waiting for White.":
    "Bàn cờ đã ổn định. Đang chờ Trắng.",

  "Board stable. Waiting for Black.":
    "Bàn cờ đã ổn định. Đang chờ Đen.",

  "Waiting for White.": "Đang chờ Trắng.",
  "Waiting for Black.": "Đang chờ Đen.",
};

const PIECE_TRANSLATIONS: Record<string, string> = {
  Pawn: "Tốt",
  Knight: "Mã",
  Bishop: "Tượng",
  Rook: "Xe",
  Queen: "Hậu",
  King: "Vua",
};

function translateDynamic(value: string): string | undefined {

  let match: RegExpExecArray | null;

  match = /^Loaded: (.+)$/.exec(value);

  if (match) {
    return `Đã tải: ${match[1]}`;
  }

  match = /^Open Game #(\d+) · Replay \/ Analyze$/.exec(value);

  if (match) {
    return `Mở ván #${match[1]} · Phát lại / Phân tích`;
  }

  match = /^Replay and analyze game (\d+)$/.exec(value);

  if (match) {
    return `Phát lại và phân tích ván ${match[1]}`;
  }

  match = /^Position (\d+) of (\d+)$/.exec(value);

  if (match) {
    return `Vị trí ${match[1]} trên ${match[2]}`;
  }

  match = /^Evaluation for White: (.+)$/.exec(value);

  if (match) {
    return `Đánh giá cho Trắng: ${match[1]}`;
  }

  match = /^Stockfish suggests (.+)$/.exec(value);

  if (match) {
    return `Stockfish đề xuất ${match[1]}`;
  }

  match = /^Played: (.+)$/.exec(value);

  if (match) {
    return `Đã đi: ${match[1]}`;
  }

  match = /^Best: (.+)$/.exec(value);

  if (match) {
    return `Tốt nhất: ${match[1]}`;
  }

  match = /^Opening: (.+)$/.exec(value);

  if (match) {
    return `Khai cuộc: ${match[1]}`;
  }

  match = /^(Brilliant|Great|Best|Excellent|Good|Book|Inaccuracy|Mistake|Miss|Blunder): (.+)$/.exec(value);

  if (match) {
    const label = VI_TRANSLATIONS[match[1]] ?? match[1];
    return `${label}: ${match[2]}`;
  }

  // Illegal move with exact piece and square information.

  match = /^(Illegal move detected|Possible illegal move): (White|Black) (Pawn|Knight|Bishop|Rook|Queen|King) from ([a-h][1-8]) to ([a-h][1-8])\.(.*)$/.exec(value);

  if (match) {

    const prefix =
      match[1] === "Illegal move detected"
        ? "Đã phát hiện nước đi không hợp lệ"
        : "Có thể có nước đi không hợp lệ";

    const color =
      match[2] === "White"
        ? "trắng"
        : "đen";

    const piece = PIECE_TRANSLATIONS[match[3]];

    let suffix = match[6] ?? "";

    suffix = suffix.replace(
      " Promotion is required on the destination square.",
      " Cần phong cấp tại ô đích.",
    );

    suffix = suffix.replace(
      " Restore the board to its previous position to continue.",
      " Hãy đưa bàn cờ về vị trí trước đó để tiếp tục.",
    );

    suffix = suffix.replace(
      " Verifying the physical board...",
      " Đang xác minh bàn cờ vật lý...",
    );

    return (
      `${prefix}: ${piece} ${color} ` +
      `từ ${match[4]} đến ${match[5]}.${suffix}`
    );
  }

  match = /^Bot move: (.+)\. Play this move on the physical board\.$/.exec(value);

  if (match) {
    return `Nước đi của bot: ${match[1]}. Hãy thực hiện nước đi này trên bàn cờ vật lý.`;
  }

  match = /^Detected bot move (.+)\. Verifying once more\.\.\.$/.exec(value);

  if (match) {
    return `Đã nhận diện nước đi ${match[1]} của bot. Đang xác minh thêm một lần...`;
  }

  match = /^Detected (.+)\. Verifying once more\.\.\.$/.exec(value);

  if (match) {
    return `Đã nhận diện ${match[1]}. Đang xác minh thêm một lần...`;
  }

  match = /^The bot expects (.+)\. The detected physical move is different\.$/.exec(value);

  if (match) {
    return `Bot yêu cầu nước ${match[1]}. Nước đi nhận diện từ bàn cờ vật lý không khớp.`;
  }

  match = /^Move voice: (.+)$/.exec(value);

  if (match) {
    return `Giọng đọc nước đi: ${match[1]}`;
  }

  return undefined;
}

export function translateText(
  source: string,
  language: AppLanguage,
): string {

  if (language === "en" || !source) {
    return source;
  }

  const leading = source.match(/^\s*/)?.[0] ?? "";
  const trailing = source.match(/\s*$/)?.[0] ?? "";

  const end = source.length - trailing.length;

  const body = source.slice(
    leading.length,
    end,
  );

  if (!body) {
    return source;
  }

  const normalized = body.replace(/\s+/g, " ");

  const translated =
    VI_TRANSLATIONS[normalized] ??
    translateDynamic(normalized);

  if (translated === undefined) {
    return source;
  }

  return `${leading}${translated}${trailing}`;
}

// ============================================================
// LEGACY PAGE TRANSLATION
// ============================================================

interface TranslationState {
  original: string;
  last: string;
}

const textNodeStates = new WeakMap<Text, TranslationState>();

const attributeStates = new WeakMap<
  Element,
  Map<string, TranslationState>
>();

const TRANSLATABLE_ATTRIBUTES = [
  "aria-label",
  "title",
  "placeholder",
  "alt",
];

const IGNORE_SELECTOR = [
  "script",
  "style",
  "textarea",
  "code",
  "svg",
  "[data-i18n-ignore]",
  ".fen-code",
  ".game-player",
  ".review-player-details strong",
  ".review-accuracy-grid span",
  ".pgn-import-tag-list",
  ".review-move-san",
  ".move-row",
  ".move-list",
  ".live-player strong",
  ".live-preview-player strong",
  ".pgn-import-match strong",
].join(",");

function isIgnoredElement(element: Element): boolean {
  return element.closest(IGNORE_SELECTOR) !== null;
}

function translateTextNode(
  node: Text,
  language: AppLanguage,
): void {

  const parent = node.parentElement;

  if (!parent || isIgnoredElement(parent)) {
    return;
  }

  const current = node.nodeValue ?? "";
  const previous = textNodeStates.get(node);

  const original =
    previous && current === previous.last
      ? previous.original
      : current;

  const translated = translateText(
    original,
    language,
  );

  if (translated !== current) {
    node.nodeValue = translated;
  }

  textNodeStates.set(node, {
    original,
    last: translated,
  });
}

function translateElementAttributes(
  element: Element,
  language: AppLanguage,
): void {

  if (isIgnoredElement(element)) {
    return;
  }

  let states = attributeStates.get(element);

  if (!states) {
    states = new Map();
    attributeStates.set(element, states);
  }

  for (const attribute of TRANSLATABLE_ATTRIBUTES) {

    const current = element.getAttribute(attribute);

    if (current === null) {
      continue;
    }

    const previous = states.get(attribute);

    const original =
      previous && current === previous.last
        ? previous.original
        : current;

    const translated = translateText(
      original,
      language,
    );

    if (translated !== current) {
      element.setAttribute(
        attribute,
        translated,
      );
    }

    states.set(attribute, {
      original,
      last: translated,
    });
  }
}

function translateNodeTree(
  node: Node,
  language: AppLanguage,
): void {

  if (node.nodeType === Node.TEXT_NODE) {
    translateTextNode(
      node as Text,
      language,
    );
    return;
  }

  if (node.nodeType !== Node.ELEMENT_NODE) {
    return;
  }

  const element = node as Element;

  if (isIgnoredElement(element)) {
    return;
  }

  translateElementAttributes(
    element,
    language,
  );

  element.childNodes.forEach((child) => {
    translateNodeTree(
      child,
      language,
    );
  });
}

export function observeTranslatedContent(
  root: HTMLElement,
  language: AppLanguage,
): () => void {

  document.documentElement.lang = language;

  translateNodeTree(
    root,
    language,
  );

  const observer = new MutationObserver(
    (records) => {

      for (const record of records) {

        if (record.type === "characterData") {

          translateNodeTree(
            record.target,
            language,
          );

          continue;
        }

        if (record.type === "childList") {

          record.addedNodes.forEach((node) => {
            translateNodeTree(
              node,
              language,
            );
          });

          continue;
        }

        if (
          record.type === "attributes" &&
          record.attributeName
        ) {

          translateElementAttributes(
            record.target as Element,
            language,
          );
        }
      }
    },
  );

  observer.observe(
    root,
    {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: TRANSLATABLE_ATTRIBUTES,
    },
  );

  return () => {
    observer.disconnect();
  };
}

// ============================================================
// GLOBAL LANGUAGE CONTEXT
// ============================================================

const LanguageContext =
  createContext<LanguageContextValue | null>(null);

function getInitialLanguage(): AppLanguage {

  if (typeof window === "undefined") {
    return "en";
  }

  try {

    const saved = window.localStorage.getItem(
      STORAGE_KEY,
    );

    if (saved === "vi" || saved === "en") {
      return saved;
    }

  } catch {
    return "en";
  }

  return "en";
}

export function LanguageProvider({
  children,
}: {
  children: ReactNode;
}) {

  const [language, setLanguageState] =
    useState<AppLanguage>(
      getInitialLanguage,
    );

  const setLanguage = useCallback(
    (nextLanguage: AppLanguage) => {

      setLanguageState(nextLanguage);

      try {

        window.localStorage.setItem(
          STORAGE_KEY,
          nextLanguage,
        );

      } catch {
        // Keep the active language in React state.
      }
    },
    [],
  );

  const t = useCallback(
    (text: string) => translateText(
      text,
      language,
    ),
    [language],
  );

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      t,
    }),
    [
      language,
      setLanguage,
      t,
    ],
  );

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {

  const context = useContext(LanguageContext);

  if (!context) {
    throw new Error(
      "useLanguage must be used inside LanguageProvider.",
    );
  }

  return context;
}

// ============================================================
// GLOBAL LANGUAGE SWITCHER
// ============================================================

export function LanguageSwitcher({
  collapsed,
}: {
  collapsed: boolean;
}) {

  const {
    language,
    setLanguage,
    t,
  } = useLanguage();

  return (
    <div
      className={
        `chesscv-language-switcher${collapsed ? " is-collapsed" : ""}`
      }
      role="group"
      aria-label={t("Language")}
      data-i18n-ignore
    >

      <button
        type="button"
        className={language === "en" ? "active" : ""}
        aria-label={t("Switch to English")}
        aria-pressed={language === "en"}
        title={t("Switch to English")}
        onClick={() => setLanguage("en")}
      >
        EN
      </button>

      <button
        type="button"
        className={language === "vi" ? "active" : ""}
        aria-label={t("Switch to Vietnamese")}
        aria-pressed={language === "vi"}
        title={t("Switch to Vietnamese")}
        onClick={() => setLanguage("vi")}
      >
        VI
      </button>

    </div>
  );
}