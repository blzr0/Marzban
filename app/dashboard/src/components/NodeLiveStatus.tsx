import { Box, HStack, Text, VStack } from "@chakra-ui/react";
import { useAccordionItemState } from "@chakra-ui/react";
import { FC, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNodeStatusQuery } from "contexts/NodesContext";

const formatUptime = (seconds: number): string => {
  const total = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${secs}s`;
  return `${secs}s`;
};

type DotState = "ok" | "bad" | "unknown";

const dotColor: Record<DotState, string> = { ok: "green", bad: "red", unknown: "gray" };

const StatusDot: FC<{ state: DotState }> = ({ state }) => {
  const c = dotColor[state];
  return (
    <Box
      w="8px"
      h="8px"
      borderRadius="full"
      flexShrink={0}
      bg={`${c}.400`}
      boxShadow={`0 0 0 3px var(--chakra-colors-${c}-100)`}
      _dark={{ boxShadow: `0 0 0 3px var(--chakra-colors-${c}-700)` }}
    />
  );
};

const Card: FC<{ children: ReactNode }> = ({ children }) => {
  const { t } = useTranslation();
  return (
    <Box
      w="full"
      mb={3}
      p={3}
      borderRadius="6px"
      bg="gray.50"
      _dark={{ bg: "gray.750", borderColor: "gray.600" }}
      border="1px solid"
      borderColor="gray.200"
    >
      <Text
        fontSize="10px"
        fontWeight="bold"
        letterSpacing="wide"
        textTransform="uppercase"
        color="gray.500"
        _dark={{ color: "gray.400" }}
        mb={2}
      >
        {t("nodes.status.liveTitle")}
      </Text>
      {children}
    </Box>
  );
};

type Props = {
  nodeId?: number | null;
};

export const NodeLiveStatus: FC<Props> = ({ nodeId }) => {
  const { t } = useTranslation();
  const { isOpen } = useAccordionItemState();
  const { data, isError } = useNodeStatusQuery(nodeId, isOpen);

  if (!nodeId || !isOpen) return null;

  // Couldn't get a status at all - from the panel (isError) or from the node
  // (reachable=false). Either way Xray's actual state is unknown, which is not
  // the same as "not running", so don't paint it red.
  if (isError || (data && !data.reachable)) {
    return (
      <Card>
        <HStack fontSize="xs" spacing={2}>
          <StatusDot state="unknown" />
          <Text fontWeight="semibold" color="gray.600" _dark={{ color: "gray.300" }}>
            {t("nodes.status.unknown")}
          </Text>
        </HStack>
        {data?.last_error && (
          <Text
            mt={1}
            fontSize="xs"
            color="gray.500"
            _dark={{ color: "gray.400" }}
            isTruncated
            title={data.last_error}
          >
            {data.last_error}
          </Text>
        )}
      </Card>
    );
  }

  if (!data) {
    return (
      <Text fontSize="xs" color="gray.500" _dark={{ color: "gray.400" }} mb={3}>
        {t("nodes.status.loading")}
      </Text>
    );
  }

  const sockets = data.listening_sockets || [];

  return (
    <Card>
      <VStack align="stretch" spacing={1}>
        <HStack fontSize="xs" spacing={2}>
          <Text w="105px" flexShrink={0} color="gray.500" _dark={{ color: "gray.400" }}>
            {t("nodes.status.xrayProcess")}
          </Text>
          <StatusDot state={data.xray_running ? "ok" : "bad"} />
          <Text fontWeight="semibold" color={data.xray_running ? "green.500" : "red.500"}>
            {data.xray_running ? t("nodes.status.running") : t("nodes.status.notRunning")}
          </Text>
          {data.xray_running && (
            <Text color="gray.500" _dark={{ color: "gray.400" }}>
              {t("nodes.status.pidUptime", {
                pid: data.xray_pid,
                uptime: formatUptime(data.xray_uptime_seconds),
              })}
            </Text>
          )}
          {!data.xray_running && data.last_error && (
            <Text color="red.500" isTruncated title={data.last_error}>
              ({t("nodes.status.lastError")}: {data.last_error})
            </Text>
          )}
        </HStack>

        <HStack fontSize="xs" spacing={2}>
          <Text w="105px" flexShrink={0} color="gray.500" _dark={{ color: "gray.400" }}>
            {t("nodes.status.xrayApi")}
          </Text>
          <StatusDot state={data.xray_api_reachable ? "ok" : "bad"} />
          <Text fontWeight="semibold" color={data.xray_api_reachable ? "green.500" : "red.500"}>
            {data.xray_api_reachable ? t("nodes.status.reachable") : t("nodes.status.unreachable")}
          </Text>
        </HStack>

        {data.last_restart_reason && (
          <HStack fontSize="xs" spacing={2}>
            <Text w="105px" flexShrink={0} color="gray.500" _dark={{ color: "gray.400" }}>
              {t("nodes.status.lastRestart")}
            </Text>
            <Text color="gray.600" _dark={{ color: "gray.300" }}>
              {t(`nodes.status.reason.${data.last_restart_reason}`, {
                defaultValue: data.last_restart_reason,
              })}
            </Text>
          </HStack>
        )}
      </VStack>

      {sockets.length > 0 && (
        <Box mt={3}>
          <Text
            fontSize="10px"
            fontWeight="bold"
            letterSpacing="wide"
            textTransform="uppercase"
            color="gray.500"
            _dark={{ color: "gray.400" }}
            mb={1}
          >
            {t("nodes.status.activeInbounds")}
          </Text>
          <VStack align="stretch" spacing="2px">
            {sockets.map((s, i) => (
              <HStack key={`${s.tag}-${i}`} fontSize="xs" fontFamily="mono" spacing={3}>
                <Text flex="1" isTruncated color="gray.700" _dark={{ color: "gray.300" }}>
                  {s.tag}
                </Text>
                <Text
                  w="34px"
                  textAlign="center"
                  borderRadius="4px"
                  fontWeight="bold"
                  fontSize="10px"
                  bg={s.proto === "udp" ? "cyan.50" : "blue.50"}
                  color={s.proto === "udp" ? "cyan.700" : "blue.700"}
                  _dark={{
                    bg: s.proto === "udp" ? "cyan.900" : "blue.900",
                    color: s.proto === "udp" ? "cyan.200" : "blue.200",
                  }}
                >
                  {s.proto}
                </Text>
                <Text w="50px" textAlign="right" color="gray.600" _dark={{ color: "gray.400" }}>
                  {s.port}
                </Text>
              </HStack>
            ))}
          </VStack>
        </Box>
      )}
    </Card>
  );
};
