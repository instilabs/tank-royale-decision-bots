import dev.robocode.tankroyale.runner.*;
import java.time.Duration;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

public class RunBattle {
    public static void main(String[] args) {
        Logger.getLogger("dev.robocode.tankroyale").setLevel(Level.INFO);
        try (var runner = BattleRunner.create(b -> {
            b.embeddedServer();
            b.botConnectTimeout(Duration.ofSeconds(60));
        })) {
            var setup = BattleSetup.classic(s -> s.setNumberOfRounds(3));
            var bots = List.of(
                    BotEntry.of("OllayaDecima"),
                    BotEntry.of("OllayaLargha"));
            var owner = new Object();
            try (var handle = runner.startBattleAsync(setup, bots)) {
                handle.getOnGameStarted().on(owner, e -> System.out.println("game started"));
                var results = handle.awaitResults();
                System.out.printf("Results (%d rounds):%n", results.getNumberOfRounds());
                for (var bot : results.getResults())
                    System.out.printf("  #%d  %-20s  %d pts%n", bot.getRank(), bot.getName(), bot.getTotalScore());
            }
        }
    }
}
