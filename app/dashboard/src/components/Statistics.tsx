import { Box, BoxProps, Card, chakra, HStack, Text } from "@chakra-ui/react";
import {
  ChartBarIcon,
  CpuChipIcon,
  ServerStackIcon,
  UsersIcon,
} from "@heroicons/react/24/outline";
import { useDashboard } from "contexts/DashboardContext";
import { FC, PropsWithChildren, ReactElement, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "react-query";
import { fetch } from "service/http";
import { formatBytes, numberWithCommas } from "utils/formatByte";

const TotalUsersIcon = chakra(UsersIcon, {
  baseStyle: { w: 5, h: 5, position: "relative", zIndex: "2" },
});
const NetworkIcon = chakra(ChartBarIcon, {
  baseStyle: { w: 5, h: 5, position: "relative", zIndex: "2" },
});
const CpuIcon = chakra(CpuChipIcon, {
  baseStyle: { w: 5, h: 5, position: "relative", zIndex: "2" },
});
const NodesIcon = chakra(ServerStackIcon, {
  baseStyle: { w: 5, h: 5, position: "relative", zIndex: "2" },
});

type StatisticCardProps = {
  title: string;
  content: ReactNode;
  icon: ReactElement;
};

const StatisticCard: FC<PropsWithChildren<StatisticCardProps>> = ({
  title,
  content,
  icon,
}) => {
  return (
    <Card
      p={6}
      borderWidth="1px"
      borderColor="light-border"
      bg="#F9FAFB"
      _dark={{ borderColor: "gray.600", bg: "gray.750" }}
      borderStyle="solid"
      boxShadow="none"
      borderRadius="12px"
      width="full"
      display="flex"
      justifyContent="space-between"
      alignItems="center"
      flexDirection="row"
      h="full"
    >
      <HStack alignItems="center" columnGap="4">
        <Box
          p="2"
          position="relative"
          color="white"
          _before={{
            content: `""`,
            position: "absolute",
            top: 0,
            left: 0,
            bg: "primary.400",
            display: "block",
            w: "full",
            h: "full",
            borderRadius: "5px",
            opacity: ".5",
            z: "1",
          }}
          _after={{
            content: `""`,
            position: "absolute",
            top: "-5px",
            left: "-5px",
            bg: "primary.400",
            display: "block",
            w: "calc(100% + 10px)",
            h: "calc(100% + 10px)",
            borderRadius: "8px",
            opacity: ".4",
            z: "1",
          }}
        >
          {icon}
        </Box>
        <Text
          color="gray.600"
          _dark={{ color: "gray.300" }}
          fontWeight="medium"
          textTransform="capitalize"
          fontSize="sm"
        >
          {title}
        </Text>
      </HStack>
      <Box fontSize="3xl" fontWeight="semibold">
        {content}
      </Box>
    </Card>
  );
};

const SubLine: FC<PropsWithChildren<{ color?: string }>> = ({ children, color }) => (
  <Text
    fontSize="sm"
    fontWeight="medium"
    textAlign="right"
    color={color || "gray.500"}
    _dark={{ color: color ? color.replace(".500", ".300") : "gray.400" }}
  >
    {children}
  </Text>
);

const MainValue: FC<{ value: ReactNode; suffix?: ReactNode }> = ({ value, suffix }) => (
  <HStack alignItems="flex-end" justifyContent="flex-end" spacing={1}>
    <Text lineHeight="1.1">{value}</Text>
    {suffix && (
      <Text fontWeight="normal" fontSize="lg" as="span" display="inline-block">
        {suffix}
      </Text>
    )}
  </HStack>
);

export const StatisticsQueryKey = "statistics-query-key";
export const Statistics: FC<BoxProps> = (props) => {
  const { version, onEditingNodes } = useDashboard();
  const { data: systemData } = useQuery({
    queryKey: StatisticsQueryKey,
    queryFn: () => fetch("/system"),
    refetchInterval: 5000,
    onSuccess: ({ version: currentVersion }) => {
      if (version !== currentVersion)
        useDashboard.setState({ version: currentVersion });
    },
  });
  const { t } = useTranslation();
  // Node counts are only sent to sudo admins
  const showNodes = systemData && systemData.nodes_total != null;
  const nodesDown = showNodes ? systemData.nodes_total - systemData.nodes_connected : 0;
  return (
    <Box
      display="grid"
      gridTemplateColumns={{
        base: "1fr",
        md: "repeat(2, 1fr)",
        xl: `repeat(${showNodes ? 4 : 3}, 1fr)`,
      }}
      gap={4}
      {...props}
    >
      <StatisticCard
        title={t("activeUsers")}
        content={
          systemData && (
            <Box>
              <MainValue
                value={numberWithCommas(systemData.users_active)}
                suffix={`/ ${numberWithCommas(systemData.total_user)}`}
              />
              <SubLine color="green.500">
                {t("statistics.onlineNow", { count: systemData.online_now })}
              </SubLine>
            </Box>
          )
        }
        icon={<TotalUsersIcon />}
      />
      <StatisticCard
        title={t("dataUsage")}
        content={
          systemData && (
            <Box>
              <MainValue
                value={formatBytes(systemData.incoming_bandwidth + systemData.outgoing_bandwidth)}
              />
              {systemData.usage_24h != null && (
                <SubLine>
                  {t("statistics.last24h", { usage: formatBytes(systemData.usage_24h) })}
                </SubLine>
              )}
            </Box>
          )
        }
        icon={<NetworkIcon />}
      />
      {showNodes && (
        <Box
          as="button"
          display="block"
          w="full"
          textAlign="left"
          onClick={() => onEditingNodes(true)}
          borderRadius="12px"
          _hover={{ opacity: 0.85 }}
        >
          <StatisticCard
            title={t("statistics.nodes")}
            content={
              <Box>
                <MainValue
                  value={systemData.nodes_connected}
                  suffix={`/ ${systemData.nodes_total}`}
                />
                <SubLine color={nodesDown ? "red.500" : "green.500"}>
                  {nodesDown
                    ? t("statistics.nodesDown", { count: nodesDown })
                    : t("statistics.allNodesUp")}
                </SubLine>
              </Box>
            }
            icon={<NodesIcon />}
          />
        </Box>
      )}
      <StatisticCard
        title={t("statistics.master")}
        content={
          systemData && (
            <Box>
              <MainValue
                value={`${systemData.cpu_usage.toFixed(1)}%`}
                suffix={`${systemData.cpu_cores} cores`}
              />
              <SubLine>
                RAM {formatBytes(systemData.mem_used, 1)} / {formatBytes(systemData.mem_total, 1)}
              </SubLine>
            </Box>
          )
        }
        icon={<CpuIcon />}
      />
    </Box>
  );
};
