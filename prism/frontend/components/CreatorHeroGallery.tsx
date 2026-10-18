import Image from "next/image";
import Link from "next/link";
import styles from "./CreatorHeroGallery.module.css";

const portraits = [
  { name: "Ray Dalio", username: "ray_dalio", image: "/creators/ray-dalio.png", position: "ray" },
  { name: "Bryson DeChambeau", username: "bryson_dechambeau", image: "/creators/bryson-dechambeau.png", position: "bryson" },
  { name: "Luka Modrić", username: "luka_modric", image: "/creators/luka-modric.png", position: "luka" },
  { name: "José Alvarado", username: "jose_alvarado", image: "/creators/jose-alvarado.png", position: "jose" },
  { name: "Bill Gates", username: "bill_gates", image: "/creators/bill-gates.png", position: "bill" },
  { name: "Mark Cuban", username: "mark_cuban", image: "/creators/mark-cuban.png", position: "mark" },
] as const;

export function CreatorHeroGallery() {
  return (
    <div className={styles.gallery} role="group" aria-label="Explore creator profiles">
      <div className={styles.orbit} aria-hidden="true" />
      {portraits.map(({ name, username, image, position }) => (
        <Link
          key={username}
          href={`/users/${username}`}
          aria-label={`Explore ${name}'s profile`}
          title={name}
          className={`${styles.portrait} ${styles[position]}`}
        >
          <Image
            src={image}
            alt={`Illustrated portrait of ${name}`}
            fill
            sizes="(max-width: 760px) 35vw, 180px"
            className={styles.image}
            priority={position === "bill" || position === "mark" || position === "jose"}
          />
        </Link>
      ))}
    </div>
  );
}
