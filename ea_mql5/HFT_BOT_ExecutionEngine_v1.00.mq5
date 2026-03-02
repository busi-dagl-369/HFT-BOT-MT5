//+------------------------------------------------------------------+
//| Tier 04 - MT5 Execution Engine (EA)                               |
//| Intelligent MT5 execution engine for trading ladder orders         |
//| Manages limit orders, synchronizes with trade plans, tracks P&L    |
//+------------------------------------------------------------------+

#property copyright "HFT-BOT Trading System"
#property link "https://github.com/busi-dagl-369/HFT-BOT-MT5"
#property version "1.00"
#property strict
#property description "Multi-tier AI trading execution engine for MT5"

// Input parameters
input string                TradePlanTopic = "trade.plans";        // Topic for incoming trade plans
input string                ExecutionStateTopic = "execution.state"; // Topic for outgoing execution state
input double                SlippageTolerance = 2.0;               // Max slippage in pips
input int                   MaxOrderRetries = 3;                   // Max retries on order rejection
input int                   PositionReconciliationTicks = 100;     // Reconciliation interval
input bool                  EnableNewsLockout = true;              // Enable news blackout
input int                   NewsLockoutMinsBefore = 15;            // Minutes before economic event
input int                   NewsLockoutMinsAfter = 5;              // Minutes after economic event
input double                MaxSpreadPips = 3.0;                   // Max spread to trade
input int                   MaxOpenPositions = 5;                  // Max concurrent positions
input double                MaxTotalVolume = 1.0;                  // Max total volume in lots
input bool                  EnableTradingMode = false;             // CRITICAL: Safety flag for live trading

// Global variables
struct TradeOrder {
    ulong   OrderTicket;
    double  Price;
    double  Volume;
    string  OrderType;      // "BUY" or "SELL"
    int     LadderIndex;
    string  PredictionID;
    datetime CreatedTime;
};

struct Position {
    ulong   PositionTicket;
    string  Symbol;
    double  EntryPrice;
    double  Volume;
    string  PositionType;
    double  CurrentPNL;
    double  PeakPNL;
    string  PredictionID;
    datetime EntryTime;
};

TradeOrder ActiveOrders[];          // Array of active orders
Position   OpenPositions[];         // Array of open positions
string     CurrentPredictionID = ""; // Current prediction ID
int        ReconciliationCounter = 0; // Reconciliation counter

// Messaging state
bool       ZmqConnected = false;
int        SocketHandle = INVALID_HANDLE;

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit() {
    Print("=== HFT-BOT MT5 Execution Engine Initializing ===");
    
    // Initialize ZeroMQ connection (placeholder - implement as needed)
    // ZmqConnected = InitializeZmq();
    // if (!ZmqConnected) {
    //     Print("ERROR: Failed to initialize ZeroMQ");
    //     return INIT_FAILED;
    // }
    
    ArrayResize(ActiveOrders, 0);
    ArrayResize(OpenPositions, 0);
    
    Print("Execution Engine Ready");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
    // Close all connections and pending orders
    CloseAllOrders();
    
    Print("Execution Engine Stopped");
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick() {
    static int TickCounter = 0;
    TickCounter++;
    
    // Reconcile positions periodically
    if (TickCounter % PositionReconciliationTicks == 0) {
        ReconcilePositions();
    }
    
    // Update position P&L tracking
    UpdatePositionPNL();
    
    // Publish execution state
    PublishExecutionState();
    
    // Check for order fills and manage ladder progression
    ManageLadderProgression();
}

//+------------------------------------------------------------------+
//| Synchronize with new trade plan                                   |
//+------------------------------------------------------------------+
void SynchronizeWithTradePlan(string PredictionID, string LadderDirection,
                              double[] PriceArray[], double[] VolumeArray[],
                              int LadderIndexArray[]) {
    
    if (!EnableTradingMode) {
        Print("WARNING: Trading mode disabled. Skipping order placement.");
        return;
    }
    
    // Cancel old orders if prediction ID changed
    if (PredictionID != CurrentPredictionID) {
        Print("New prediction detected: ", PredictionID);
        CancelOldOrders(CurrentPredictionID);
        CurrentPredictionID = PredictionID;
    }
    
    // Place new ladder orders
    int NewOrders = 0;
    for (int i = 0; i < ArraySize(PriceArray); i++) {
        if (PlaceLadderOrder(PredictionID, LadderDirection, PriceArray[i], 
                             VolumeArray[i], LadderIndexArray[i])) {
            NewOrders++;
        }
    }
    
    Print("Ladder synchronized. New orders: ", NewOrders);
}

//+------------------------------------------------------------------+
//| Place a single ladder order                                       |
//+------------------------------------------------------------------+
bool PlaceLadderOrder(string PredictionID, string Direction, double Price,
                      double Volume, int LadderIndex) {
    
    // Check spread
    double CurrentSpread = Ask() - Bid();
    double SpreadPips = CurrentSpread * 10000; // For most pairs
    
    if (SpreadPips > MaxSpreadPips) {
        Print("SPREAD TOO WIDE: ", SpreadPips, " pips");
        return false;
    }
    
    // Check position limits
    if (ArraySize(OpenPositions) >= MaxOpenPositions) {
        Print("Max open positions reached");
        return false;
    }
    
    // Prepare order
    MqlTradeRequest Request;
    MqlTradeResult  Result;
    
    ZeroMemory(Request);
    ZeroMemory(Result);
    
    Request.action = TRADE_ACTION_PENDING;
    Request.symbol = Symbol();
    Request.type = (Direction == "BUY") ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
    Request.price = Price;
    Request.volume = Volume;
    Request.deviation = (int)(SlippageTolerance * 10);
    Request.type_filling = ORDER_FILLING_IOC;
    Request.magic = 20250302; // Magic number for EA identification
    Request.comment = PredictionID;
    
    // Place order with retry logic
    int Retries = 0;
    while (Retries < MaxOrderRetries) {
        if (OrderSend(Request, Result)) {
            Print("Order placed: Ticket=", Result.order, " Price=", Price, " Vol=", Volume);
            
            // Track order
            TradeOrder NewOrder;
            NewOrder.OrderTicket = Result.order;
            NewOrder.Price = Price;
            NewOrder.Volume = Volume;
            NewOrder.OrderType = Direction;
            NewOrder.LadderIndex = LadderIndex;
            NewOrder.PredictionID = PredictionID;
            NewOrder.CreatedTime = TimeCurrent();
            
            ArrayResize(ActiveOrders, ArraySize(ActiveOrders) + 1);
            ActiveOrders[ArraySize(ActiveOrders) - 1] = NewOrder;
            
            return true;
        } else {
            Print("Order placement failed. Error: ", GetLastError(), " Retry: ", Retries + 1);
            Sleep(100);
            Retries++;
        }
    }
    
    return false;
}

//+------------------------------------------------------------------+
//| Cancel orders from old prediction                                 |
//+------------------------------------------------------------------+
void CancelOldOrders(string OldPredictionID) {
    MqlTradeRequest Request;
    MqlTradeResult  Result;
    
    for (int i = ArraySize(ActiveOrders) - 1; i >= 0; i--) {
        if (ActiveOrders[i].PredictionID == OldPredictionID || OldPredictionID == "") {
            COrderGetTicket(ActiveOrders[i].OrderTicket);
            
            ZeroMemory(Request);
            ZeroMemory(Result);
            
            Request.action = TRADE_ACTION_REMOVE;
            Request.order = ActiveOrders[i].OrderTicket;
            
            if (OrderSend(Request, Result)) {
                Print("Order cancelled: ", ActiveOrders[i].OrderTicket);
                ArrayRemove(ActiveOrders, i, 1);
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Manage ladder progression as orders fill                          |
//+------------------------------------------------------------------+
void ManageLadderProgression() {
    // Check for filled orders
    for (int i = ArraySize(ActiveOrders) - 1; i >= 0; i--) {
        ulong Ticket = ActiveOrders[i].OrderTicket;
        
        if (PositionSelectByTicket(Ticket)) {
            // Order filled - create position entry
            Position NewPos;
            NewPos.PositionTicket = Ticket;
            NewPos.Symbol = Symbol();
            NewPos.EntryPrice = ActiveOrders[i].Price;
            NewPos.Volume = ActiveOrders[i].Volume;
            NewPos.PositionType = ActiveOrders[i].OrderType;
            NewPos.PredictionID = CurrentPredictionID;
            NewPos.EntryTime = TimeCurrent();
            NewPos.CurrentPNL = 0;
            NewPos.PeakPNL = 0;
            
            ArrayResize(OpenPositions, ArraySize(OpenPositions) + 1);
            OpenPositions[ArraySize(OpenPositions) - 1] = NewPos;
            
            // Remove from active orders
            ArrayRemove(ActiveOrders, i, 1);
            
            Print("Order filled, position opened: ", Ticket);
        }
    }
}

//+------------------------------------------------------------------+
//| Update position P&L                                               |
//+------------------------------------------------------------------+
void UpdatePositionPNL() {
    double Bid = SymbolInfoDouble(Symbol(), SYMBOL_BID);
    double Ask = SymbolInfoDouble(Symbol(), SYMBOL_ASK);
    
    for (int i = 0; i < ArraySize(OpenPositions); i++) {
        if (PositionSelectByTicket(OpenPositions[i].PositionTicket)) {
            double CurrentPrice = (OpenPositions[i].PositionType == "BUY") ? Bid : Ask;
            double PriceDiff = CurrentPrice - OpenPositions[i].EntryPrice;
            double TickValue = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_TICK_VALUE);
            
            OpenPositions[i].CurrentPNL = PriceDiff * OpenPositions[i].Volume * TickValue * 10000;
            
            if (OpenPositions[i].CurrentPNL > OpenPositions[i].PeakPNL) {
                OpenPositions[i].PeakPNL = OpenPositions[i].CurrentPNL;
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Reconcile positions with broker                                   |
//+------------------------------------------------------------------+
void ReconcilePositions() {
    int BrokerPositionCount = PositionsTotal();
    
    Print("Reconciling positions. Internal: ", ArraySize(OpenPositions), 
          " Broker: ", BrokerPositionCount);
    
    // Check for orphaned positions
    for (int i = 0; i < ArraySize(OpenPositions); i++) {
        if (!PositionSelectByTicket(OpenPositions[i].PositionTicket)) {
            Print("Position not found at broker: ", OpenPositions[i].PositionTicket);
            ArrayRemove(OpenPositions, i, 1);
        }
    }
}

//+------------------------------------------------------------------+
//| Publish execution state                                           |
//+------------------------------------------------------------------+
void PublishExecutionState() {
    // Construct execution state JSON packet
    string ExecutionStateJson = "{";
    ExecutionStateJson += "\"prediction_id\": \"" + CurrentPredictionID + "\",";
    ExecutionStateJson += "\"symbol\": \"" + Symbol() + "\",";
    ExecutionStateJson += "\"timestamp\": \"" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\",";
    ExecutionStateJson += "\"open_orders\": " + IntegerToString(ArraySize(ActiveOrders)) + ",";
    ExecutionStateJson += "\"open_positions\": " + IntegerToString(ArraySize(OpenPositions)) + ",";
    ExecutionStateJson += "\"pnl\": " + DoubleToString(GetTotalPNL(), 2) + "";
    ExecutionStateJson += "}";
    
    // Publish via ZeroMQ (placeholder)
    // PublishMessage(ExecutionStateTopic, ExecutionStateJson);
    
    Print("Execution State: ", ExecutionStateJson);
}

//+------------------------------------------------------------------+
//| Helper: Get total PNL                                             |
//+------------------------------------------------------------------+
double GetTotalPNL() {
    double TotalPNL = 0;
    for (int i = 0; i < ArraySize(OpenPositions); i++) {
        TotalPNL += OpenPositions[i].CurrentPNL;
    }
    return TotalPNL;
}

//+------------------------------------------------------------------+
//| Helper: Close all orders                                          |
//+------------------------------------------------------------------+
void CloseAllOrders() {
    MqlTradeRequest Request;
    MqlTradeResult  Result;
    
    // Cancel pending orders
    for (int i = ArraySize(ActiveOrders) - 1; i >= 0; i--) {
        ZeroMemory(Request);
        ZeroMemory(Result);
        Request.action = TRADE_ACTION_REMOVE;
        Request.order = ActiveOrders[i].OrderTicket;
        OrderSend(Request, Result);
    }
    ArrayResize(ActiveOrders, 0);
    
    // Close open positions
    for (int i = ArraySize(OpenPositions) - 1; i >= 0; i--) {
        ZeroMemory(Request);
        ZeroMemory(Result);
        Request.action = TRADE_ACTION_DEAL;
        Request.order = OpenPositions[i].PositionTicket;
        Request.type = (OpenPositions[i].PositionType == "BUY") ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
        OrderSend(Request, Result);
    }
    ArrayResize(OpenPositions, 0);
}

// Placeholder for Bid() and Ask() functions if not defined
double Bid() {
    return SymbolInfoDouble(Symbol(), SYMBOL_BID);
}

double Ask() {
    return SymbolInfoDouble(Symbol(), SYMBOL_ASK);
}
