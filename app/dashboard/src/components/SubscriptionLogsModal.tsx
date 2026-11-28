import {
  Box,
  Button,
  HStack,
  IconButton,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tooltip,
  Tr,
  VStack,
  chakra,
  useColorMode,
} from "@chakra-ui/react";
import { ArrowPathIcon, DocumentTextIcon } from "@heroicons/react/24/outline";
import { useDashboard } from "contexts/DashboardContext";
import debounce from "lodash.debounce";
import { FC, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetch } from "service/http";
import { SubscriptionLog, SubscriptionLogStatus } from "types/User";
import { Icon } from "./Icon";
import {
  LogStatusBadge,
  TruncatedCell,
  deviceLine,
  formatLogTime,
} from "./SubscriptionLogCells";

const LogsIcon = chakra(DocumentTextIcon, {
  baseStyle: {
    w: 5,
    h: 5,
  },
});
const RefreshIcon = chakra(ArrowPathIcon, {
  baseStyle: {
    w: 4,
    h: 4,
  },
});

const PAGE_SIZE = 50;
const STATUSES: SubscriptionLogStatus[] = [
  "ok",
  "hwid_limit_exceeded",
  "hwid_missing",
  "expired",
  "revoked",
];

type Filters = {
  username: string;
  hwid: string;
  status: SubscriptionLogStatus | "";
};

export const SubscriptionLogsModal: FC = () => {
  const { subscriptionLogsUsername, onShowingSubscriptionLogs } = useDashboard();
  const isOpen = subscriptionLogsUsername !== null;
  const { t } = useTranslation();
  const { colorMode } = useColorMode();

  const [filters, setFilters] = useState<Filters>({ username: "", hwid: "", status: "" });
  // text inputs update `filters` with a debounce, so typing doesn't fire a request per key
  const [inputs, setInputs] = useState({ username: "", hwid: "" });
  const [page, setPage] = useState(0);
  const [logs, setLogs] = useState<SubscriptionLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  // only the latest request may fill the table: filters can change mid-flight
  const lastRequest = useRef(0);

  useEffect(() => {
    if (isOpen) {
      const username = subscriptionLogsUsername || "";
      setInputs({ username, hwid: "" });
      setFilters({ username, hwid: "", status: "" });
      setPage(0);
    }
  }, [subscriptionLogsUsername]);

  const load = () => {
    if (!isOpen) return;
    const query: Record<string, string | number> = {
      offset: page * PAGE_SIZE,
      limit: PAGE_SIZE,
    };
    if (filters.username) query.username = filters.username;
    if (filters.hwid) query.hwid = filters.hwid;
    if (filters.status) query.status = filters.status;
    const request = ++lastRequest.current;
    setLoading(true);
    fetch<{ logs: SubscriptionLog[]; total: number }>("/subscription-logs", { query })
      .then((data) => {
        if (request !== lastRequest.current) return;
        setLogs(data.logs);
        setTotal(data.total);
      })
      .catch(() => {
        if (request !== lastRequest.current) return;
        setLogs([]);
        setTotal(0);
      })
      .finally(() => {
        if (request === lastRequest.current) setLoading(false);
      });
  };

  useEffect(load, [isOpen, filters, page]);

  const applyText = useMemo(
    () =>
      debounce((next: { username: string; hwid: string }) => {
        setPage(0);
        setFilters((f) => ({ ...f, ...next }));
      }, 400),
    []
  );

  const onText = (key: "username" | "hwid", value: string) => {
    const next = { ...inputs, [key]: value };
    setInputs(next);
    applyText(next);
  };

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Modal isOpen={isOpen} onClose={() => onShowingSubscriptionLogs(null)} size="6xl">
      <ModalOverlay bg="blackAlpha.300" backdropFilter="blur(10px)" />
      <ModalContent mx="3" w="full">
        <ModalHeader pt={6}>
          <HStack gap={2}>
            <Icon color="primary">
              <LogsIcon color="white" />
            </Icon>
            <Text fontWeight="semibold" fontSize="lg">
              {t("subscriptionLogs.title")}
            </Text>
          </HStack>
        </ModalHeader>
        <ModalCloseButton mt={3} />
        <ModalBody>
          <VStack align="stretch" spacing={3}>
            <HStack flexWrap="wrap" gap={2} spacing={0}>
              <Input
                size="sm"
                maxW="200px"
                borderRadius="6px"
                placeholder={t("subscriptionLogs.filterUsername")}
                value={inputs.username}
                onChange={(e) => onText("username", e.target.value)}
              />
              <Input
                size="sm"
                maxW="200px"
                borderRadius="6px"
                placeholder={t("subscriptionLogs.filterHwid")}
                value={inputs.hwid}
                onChange={(e) => onText("hwid", e.target.value)}
              />
              <Select
                size="sm"
                maxW="220px"
                borderRadius="6px"
                value={filters.status}
                onChange={(e) => {
                  setPage(0);
                  setFilters((f) => ({
                    ...f,
                    status: e.target.value as SubscriptionLogStatus | "",
                  }));
                }}
                sx={{
                  option: {
                    backgroundColor: colorMode === "dark" ? "#222C3B" : "white",
                  },
                }}
              >
                <option value="">{t("subscriptionLogs.allStatuses")}</option>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {t(`subscriptionLogs.status.${s}`)}
                  </option>
                ))}
              </Select>
              <Tooltip label={t("subscriptionLogs.refresh")}>
                <IconButton
                  aria-label={t("subscriptionLogs.refresh")}
                  size="sm"
                  variant="outline"
                  onClick={load}
                >
                  {loading ? <Spinner size="xs" /> : <RefreshIcon />}
                </IconButton>
              </Tooltip>
            </HStack>

            <Box overflowX="auto" borderWidth="1px" borderRadius="md">
              <Table size="sm" fontSize="xs">
                <Thead>
                  <Tr>
                    <Th>{t("subscriptionLogs.time")}</Th>
                    <Th>{t("username")}</Th>
                    <Th>{t("subscriptionLogs.statusColumn")}</Th>
                    <Th>{t("subscriptionLogs.domain")}</Th>
                    <Th>{t("subscriptionLogs.device")}</Th>
                    <Th>User-Agent</Th>
                    <Th>IP</Th>
                    <Th isNumeric>{t("subscriptionLogs.count")}</Th>
                    <Th>{t("subscriptionLogs.path")}</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {logs.map((log) => (
                    <Tr key={log.id}>
                      <Td whiteSpace="nowrap">
                        <Tooltip
                          label={`${t("subscriptionLogs.firstSeen")}: ${formatLogTime(log.created_at)}`}
                        >
                          <Text>{formatLogTime(log.updated_at)}</Text>
                        </Tooltip>
                      </Td>
                      <Td whiteSpace="nowrap" fontWeight="medium">
                        {log.username}
                      </Td>
                      <Td>
                        <LogStatusBadge status={log.status} />
                      </Td>
                      <Td>
                        <TruncatedCell value={log.host} maxW="150px" />
                      </Td>
                      <Td>
                        <VStack align="start" spacing={0}>
                          <TruncatedCell value={log.hwid} maxW="150px" copyable />
                          {deviceLine(log) && (
                            <Text color="gray.500" isTruncated maxW="150px">
                              {deviceLine(log)}
                            </Text>
                          )}
                        </VStack>
                      </Td>
                      <Td>
                        <TruncatedCell value={log.user_agent} maxW="130px" copyable />
                      </Td>
                      <Td whiteSpace="nowrap">{log.ip || "—"}</Td>
                      <Td isNumeric>{log.count}</Td>
                      <Td>
                        <TruncatedCell value={log.request_path} maxW="140px" />
                      </Td>
                    </Tr>
                  ))}
                  {!loading && logs.length === 0 && (
                    <Tr>
                      <Td colSpan={9} textAlign="center" color="gray.500" py={6}>
                        {t("subscriptionLogs.empty")}
                      </Td>
                    </Tr>
                  )}
                </Tbody>
              </Table>
            </Box>
          </VStack>
        </ModalBody>
        <ModalFooter>
          <HStack w="full" justifyContent="space-between">
            <Text fontSize="xs" color="gray.500">
              {t("subscriptionLogs.total", { total, page: page + 1, pages })}
            </Text>
            <HStack>
              <Button size="xs" isDisabled={page === 0} onClick={() => setPage(page - 1)}>
                {t("subscriptionLogs.prev")}
              </Button>
              <Button
                size="xs"
                isDisabled={page + 1 >= pages}
                onClick={() => setPage(page + 1)}
              >
                {t("subscriptionLogs.next")}
              </Button>
            </HStack>
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
