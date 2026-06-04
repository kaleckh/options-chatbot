"use client";

import { useCallback, useState } from "react";
import type { CloseTradeModalProps } from "@/components/predictions/CloseTradeModal";
import { parseNonnegativePriceInput } from "@/components/predictions/tradingDeskCloseForm";
import { fetchWithTimeout, readJsonResponseOrThrow } from "@/lib/client-json";
import type { SuggestedTrade, TrackedPosition } from "@/lib/types";
import type {
  CloseSuggestedTradeRequest,
  CloseSuggestedTradeResponse,
  CloseTrackedPositionRequest,
  CloseTrackedPositionResponse,
} from "@/lib/trading-desk/apiContracts";
import { getCloseNowPrice } from "@/lib/trading-desk/positionEvidence";
import { tradingDeskMutationHeaders } from "@/lib/trading-desk/mutationIntent";

type SubmitGuard = <T>(fn: () => Promise<T>) => Promise<T | undefined>;

type ToastApi = {
  success: (message: string) => void;
  error: (message: string) => void;
};

type UseTradingDeskCloseDialogsOptions = {
  guard: SubmitGuard;
  toast: ToastApi;
  mergeTrackedPosition: (position: TrackedPosition) => void;
  mergeSuggestedTrade: (trade: SuggestedTrade) => void;
  fetchPositions: () => Promise<void>;
  fetchSuggestedTrades: () => Promise<void>;
};

export type TradingDeskCloseDialogs = {
  openCloseForm: (position: TrackedPosition) => void;
  openCloseSuggestedTradeForm: (trade: SuggestedTrade) => void;
  trackedCloseModalProps: CloseTradeModalProps;
  suggestedCloseModalProps: CloseTradeModalProps;
};

export function useTradingDeskCloseDialogs({
  guard,
  toast,
  mergeTrackedPosition,
  mergeSuggestedTrade,
  fetchPositions,
  fetchSuggestedTrades,
}: UseTradingDeskCloseDialogsOptions): TradingDeskCloseDialogs {
  const [closingPosition, setClosingPosition] = useState<TrackedPosition | null>(null);
  const [exitPrice, setExitPrice] = useState("");
  const [closeNotes, setCloseNotes] = useState("");
  const [closingId, setClosingId] = useState<number | null>(null);
  const [closingSuggestedTrade, setClosingSuggestedTrade] = useState<SuggestedTrade | null>(null);
  const [suggestedExitPrice, setSuggestedExitPrice] = useState("");
  const [suggestedCloseNotes, setSuggestedCloseNotes] = useState("");
  const [closingSuggestedTradeId, setClosingSuggestedTradeId] = useState<number | null>(null);

  const openCloseForm = useCallback((position: TrackedPosition) => {
    setClosingPosition(position);
    const suggestedExitPrice = getCloseNowPrice(position) ?? position.last_option_price;
    setExitPrice(suggestedExitPrice != null ? suggestedExitPrice.toFixed(2) : "");
    setCloseNotes("");
  }, []);

  const cancelCloseForm = useCallback(() => {
    setClosingPosition(null);
    setExitPrice("");
    setCloseNotes("");
    setClosingId(null);
  }, []);

  const openCloseSuggestedTradeForm = useCallback((trade: SuggestedTrade) => {
    setClosingSuggestedTrade(trade);
    const suggestedExitPrice = getCloseNowPrice(trade) ?? trade.last_option_price;
    setSuggestedExitPrice(suggestedExitPrice != null ? suggestedExitPrice.toFixed(2) : "");
    setSuggestedCloseNotes("");
  }, []);

  const cancelCloseSuggestedTradeForm = useCallback(() => {
    setClosingSuggestedTrade(null);
    setSuggestedExitPrice("");
    setSuggestedCloseNotes("");
    setClosingSuggestedTradeId(null);
  }, []);

  const submitClosePosition = useCallback(async () => {
    if (!closingPosition) return;
    const parsedExitPrice = parseNonnegativePriceInput(exitPrice);
    if (parsedExitPrice == null) {
      toast.error("Enter a valid exit price of 0 or greater.");
      return;
    }
    await guard(async () => {
      setClosingId(closingPosition.id);
      try {
        const payload: CloseTrackedPositionRequest = {
          exit_price: parsedExitPrice,
          notes: closeNotes || undefined,
        };
        const res = await fetchWithTimeout(`/api/positions/${closingPosition.id}/close`, {
          method: "POST",
          headers: tradingDeskMutationHeaders("close_tracked_position"),
          body: JSON.stringify(payload),
        }, "Close tracked position");
        const data = await readJsonResponseOrThrow<CloseTrackedPositionResponse>(
          res,
          "Close tracked position"
        );
        if (data.position) {
          mergeTrackedPosition(data.position as TrackedPosition);
        }
        cancelCloseForm();
        toast.success("Tracked position closed.");
        void fetchPositions();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to close tracked position.");
      } finally {
        setClosingId(null);
      }
    });
  }, [cancelCloseForm, closeNotes, closingPosition, exitPrice, fetchPositions, guard, mergeTrackedPosition, toast]);

  const submitCloseSuggestedTrade = useCallback(async () => {
    if (!closingSuggestedTrade) return;
    const parsedExitPrice = parseNonnegativePriceInput(suggestedExitPrice);
    if (parsedExitPrice == null) {
      toast.error("Enter a valid exit price of 0 or greater.");
      return;
    }
    await guard(async () => {
      setClosingSuggestedTradeId(closingSuggestedTrade.id);
      try {
        const payload: CloseSuggestedTradeRequest = {
          exit_price: parsedExitPrice,
          notes: suggestedCloseNotes || undefined,
        };
        const res = await fetchWithTimeout(`/api/suggested-trades/${closingSuggestedTrade.id}/close`, {
          method: "POST",
          headers: tradingDeskMutationHeaders("close_suggested_trade"),
          body: JSON.stringify(payload),
        }, "Close suggested trade");
        const data = await readJsonResponseOrThrow<CloseSuggestedTradeResponse>(
          res,
          "Close suggested trade"
        );
        if (data.trade) {
          mergeSuggestedTrade(data.trade as SuggestedTrade);
        }
        cancelCloseSuggestedTradeForm();
        toast.success("Suggested trade closed.");
        void fetchSuggestedTrades();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to close suggested trade.");
      } finally {
        setClosingSuggestedTradeId(null);
      }
    });
  }, [
    cancelCloseSuggestedTradeForm,
    closingSuggestedTrade,
    fetchSuggestedTrades,
    guard,
    mergeSuggestedTrade,
    suggestedCloseNotes,
    suggestedExitPrice,
    toast,
  ]);

  return {
    openCloseForm,
    openCloseSuggestedTradeForm,
    trackedCloseModalProps: {
      item: closingPosition,
      mode: "tracked",
      exitPrice,
      notes: closeNotes,
      closingId,
      onExitPriceChange: setExitPrice,
      onNotesChange: setCloseNotes,
      onCancel: cancelCloseForm,
      onConfirm: () => void submitClosePosition(),
    },
    suggestedCloseModalProps: {
      item: closingSuggestedTrade,
      mode: "suggested",
      exitPrice: suggestedExitPrice,
      notes: suggestedCloseNotes,
      closingId: closingSuggestedTradeId,
      onExitPriceChange: setSuggestedExitPrice,
      onNotesChange: setSuggestedCloseNotes,
      onCancel: cancelCloseSuggestedTradeForm,
      onConfirm: () => void submitCloseSuggestedTrade(),
    },
  };
}
